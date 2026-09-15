#!/usr/bin/env python3
"""Week 3 · Task 2 — Does DNS actually steer you? Measure it.

Textbook §2.4.3 (records) and §2.5 (CDNs).

The lecture claims two things:

    (a) most large sites are served by a CDN, reached through a CNAME chain
    (b) DNS steers each user to a *nearby* replica

Both are testable from your laptop, and one of them is harder to prove than
the slide makes it look. Your job is to produce the evidence and a number.

    python3 task2_steering.py --collect        # gather the raw data
    python3 task2_steering.py --report         # your analysis

What you have to build
----------------------
1.  For each hostname in SITES, follow the CNAME chain to its end and record
    every hop. `--collect` should leave the raw data in out/chains.json.

2.  Decide, for each site, whether it is served by a **third party**.
    This is the hard part and there is no single right answer:

      - `www.microsoft.com` ends at `akamaiedge.net`     - clearly third party
      - `www.netflix.com`   stops inside `netflix.com`   - own CDN, not third party
      - some sites have no CNAME at all and still sit behind a CDN (anycast)
      - `foo.cloudfront.net` and `foo.s3.amazonaws.com` are both Amazon,
        but they are not the same service

    Write down the rule you used and **defend it in observation.md**. A rule
    that just compares the last two labels will be wrong on at least one of
    the sites below; find which, and say so.

3.  Ask **two different resolvers** for the same name and compare the
    addresses you get back. If DNS really steers by location, a CDN-hosted
    name should answer differently to resolvers sitting in different places.

        RESOLVERS below has your system resolver and two public ones.

    Report: of N CDN-hosted sites, how many returned a different address set
    from a different resolver? Claim (b) predicts most of them. Check it.

Pass condition
--------------
There is no fixed answer. You pass by producing, in out/report.md:

  - the table: site | chain length | final zone | third party? | your rule's verdict
  - the steering number: "X of N sites answered differently to a different resolver"
  - at least one site where your classification rule was wrong, and why
"""
import argparse
import datetime
import ipaddress
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

SITES = [
    "www.microsoft.com",     # Akamai, multi-hop
    "www.netflix.com",       # own CDN
    "www.adobe.com",
    "www.cnn.com",
    "www.apple.com",
    "www.korea.ac.kr",       # no CDN at all
    "www.stanford.edu",
    "www.bbc.co.uk",
    "www.spotify.com",
    "www.github.com",
    "www.wikipedia.org",
    "www.nytimes.com",
]

RESOLVERS = {
    "system": None,          # whatever is in your resolv.conf
    "google": "8.8.8.8",
    "quad9":  "9.9.9.9",
}

MAX_CNAME_HOPS = 20

# co.uk, ac.kr처럼 마지막 두 label만으로 등록 도메인을 판단하면
# 안 되는 suffix를 최소한 보정한다.
MULTI_LABEL_SUFFIXES = {
    "co.uk",
    "ac.kr",
    "co.kr",
}

# 사람이 CNAME 체인과 서비스 소유 관계를 조사해 판단한 값.
# 아래 값은 출발점이며, 실제 수집 결과를 보고 자신이 방어할 수 있게
# 수정하는 것이 좋다.
MANUAL_THIRD_PARTY = {
    "www.microsoft.com": True,
    "www.netflix.com": False,
    "www.adobe.com": True,
    "www.cnn.com": True,
    "www.apple.com": True,
    "www.korea.ac.kr": False,
    "www.stanford.edu": True,
    "www.bbc.co.uk": True,
    "www.spotify.com": True,
    "www.github.com": False,
    "www.wikipedia.org": False,
    "www.nytimes.com": True,
}

# CDN 사용 여부와 third-party 여부는 다르다.
# Netflix와 Wikipedia는 자체 CDN을 사용할 수 있다.
# 측정 결과를 확인한 후 필요하면 수정한다.
CDN_HOSTED = set(SITES) - {
    "www.korea.ac.kr",
}

CAPTURE_NOTES = {
    "matching_query_packet": "5",
    "matching_response_packet": "6",
    "transaction_id": "0xd6f3",
    "delegation_packet": "2",
    "answer_packet": "6",
    "largest_response_packet": "2",
    "largest_response_bytes": "383",
    "largest_response_reason":
        "The referral response contained multiple NS records and "
        "additional glue address records.",
}

def dig(name, rtype="A", server=None):
    """Run one DNS lookup and return non-empty output lines."""
    args = [
        "dig",
        "+short",
        "+time=2",
        "+tries=1",
        name,
        rtype,
    ]

    if server:
        args.insert(1, f"@{server}")

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        print(
            f"warning: timeout: {name} {rtype} via {server or 'system'}",
            file=sys.stderr,
        )
        return []

    if result.returncode != 0:
        print(
                       f"warning: dig failed: {name} {rtype} "
            f"via {server or 'system'}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return []

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

def normalize_name(name):
    return name.rstrip(".").lower()


def follow_cname_chain(name, server=None):
    """Return [original, cname1, cname2, ..., final_name]."""
    current = normalize_name(name)
    chain = [current]
    seen = {current}

    for _ in range(MAX_CNAME_HOPS):
        answers = dig(current, "CNAME", server)

        if not answers:
            return chain

        target = normalize_name(answers[0])

        if target in seen:
            raise RuntimeError(
                f"CNAME loop detected: {' -> '.join(chain + [target])}"
            )

        chain.append(target)
        seen.add(target)
        current = target

    raise RuntimeError(
        f"CNAME chain exceeded {MAX_CNAME_HOPS} hops for {name}"
    )


def ipv4_answers(name, server=None):
    """Return a sorted, duplicate-free IPv4 address list."""
    addresses = set()

    for value in dig(name, "A", server):
        candidate = value.rstrip(".")

        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            # dig +short A can also print CNAME names.
            continue

        if address.version == 4:
            addresses.add(str(address))

    return sorted(addresses)


def registrable_domain(name):
    """Small heuristic for identifying the effective base domain."""
    labels = normalize_name(name).split(".")

    if len(labels) <= 2:
        return ".".join(labels)

    last_two = ".".join(labels[-2:])

    if last_two in MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])

    return last_two


def rule_says_third_party(site, final_name):
    """Rule: different registrable domains mean third-party service."""
    return registrable_domain(site) != registrable_domain(final_name)

def site_was_steered_by_resolver(data, site):
    """같은 네트워크에서 리졸버에 따라 주소 집합이 달라졌는지 확인."""
    for measurement in data["measurements"].values():
        addresses = measurement["sites"][site]["addresses"]

        non_empty_sets = {
            tuple(sorted(values))
            for values in addresses.values()
            if values
        }

        if len(non_empty_sets) > 1:
            return True

    return False


def site_was_steered_by_network(data, site):
    """같은 리졸버가 네트워크에 따라 다른 주소를 반환했는지 확인."""
    measurements = list(data["measurements"].values())

    for resolver_name in RESOLVERS:
        non_empty_sets = set()

        for measurement in measurements:
            values = measurement["sites"][site]["addresses"][resolver_name]

            if values:
                non_empty_sets.add(tuple(sorted(values)))

        if len(non_empty_sets) > 1:
            return True

    return False

def collect(network):
    """Collect one network's CNAME chains and resolver address sets."""
    output_path = os.path.join(OUT, "chains.json")

    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as file:
            data = json.load(file)
    else:
        data = {
            "format_version": 1,
            "measurements": {},
        }

    network_result = {
        "collected_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "sites": {},
    }

    for site in SITES:
        print(f"collecting {site} on {network}...")

        try:
            # 현재 네트워크의 system resolver를 이용해 chain을 추적한다.
            chain = follow_cname_chain(site)
        except RuntimeError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            chain = [normalize_name(site)]

        answers = {}

        for resolver_name, server in RESOLVERS.items():
            answers[resolver_name] = ipv4_answers(site, server)

        network_result["sites"][site] = {
            "chain": chain,
            "final_name": chain[-1],
            "addresses": answers,
        }

    data["measurements"][network] = network_result

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    print(f"saved {output_path}")

def yes_no(value):
    return "yes" if value else "no"


def report():
    """Generate out/report.md from out/chains.json."""
    input_path = os.path.join(OUT, "chains.json")
    output_path = os.path.join(OUT, "report.md")

    if not os.path.exists(input_path):
        raise RuntimeError(
            "out/chains.json does not exist; run --collect first"
        )

    with open(input_path, encoding="utf-8") as file:
        data = json.load(file)

    networks = list(data.get("measurements", {}))

    if not networks:
        raise RuntimeError("chains.json contains no measurements")

    first_network = data["measurements"][networks[0]]

    rows = []
    mismatches = []

    for site in SITES:
        site_data = first_network["sites"][site]
        chain = site_data["chain"]
        final_name = site_data["final_name"]

        manual = MANUAL_THIRD_PARTY[site]
        predicted = rule_says_third_party(site, final_name)
        verdict = "correct" if manual == predicted else "wrong"

        if manual != predicted:
            mismatches.append(
                (site, final_name, manual, predicted)
            )

        rows.append(
            f"| {site} | {len(chain) - 1} | "
            f"{registrable_domain(final_name)} | "
            f"{yes_no(manual)} | "
            f"{yes_no(predicted)} ({verdict}) |"
        )

    changed_sites = [
        site
        for site in SITES
        if site in CDN_HOSTED
        and site_was_steered_by_resolver(data, site)
    ]

    network_changed_sites = [
        site
        for site in SITES
        if site in CDN_HOSTED
        and site_was_steered_by_network(data, site)
    ]

    lines = [
        "# Task 2 DNS and CDN Report",
        "",
        "## Measurement environments",
        "",
    ]

    for network in networks:
        collected_at = data["measurements"][network]["collected_at"]
        lines.append(f"- {network}: {collected_at}")

    if len(networks) < 2:
        lines.extend([
            "",
            "> WARNING: only one network has been collected. "
            "Run --collect from a second network.",
        ])

    lines.extend([
        "",
        "## Classification rule",
        "",
        "A site is classified as third-party when the registrable domain "
        "of the final CNAME target differs from the registrable domain "
        "of the original site. This rule cannot detect a CDN hidden "
        "behind A/AAAA anycast records and may confuse two domains "
        "owned by the same organization.",
        "",
        "## Site table",
        "",
        "| site | chain length | final zone | third party? "
        "| rule verdict |",
        "|---|---:|---|---|---|",
        *rows,
        "",
        "## Steering result",
        "",
        f"{len(changed_sites)} of {len(CDN_HOSTED)} CDN-hosted sites "
        "answered with a different non-empty address set when the "
        "resolver changed.",
        "",
        "Resolver-changed sites: "
        + (", ".join(changed_sites) if changed_sites else "none"),
        "",
        f"{len(network_changed_sites)} of {len(CDN_HOSTED)} CDN-hosted "
        "sites changed for at least one resolver when the network changed.",
        "",
        "Network-changed sites: "
        + (
            ", ".join(network_changed_sites)
            if network_changed_sites
            else "none"
        ),
        "",
        "## Known rule failures",
        "",
    ])

    if mismatches:
        for site, final_name, manual, predicted in mismatches:
            lines.append(
                f"- {site}: final target `{final_name}`; "
                f"manual={yes_no(manual)}, "
                f"rule={yes_no(predicted)}. "
                "The domain-name heuristic does not fully represent "
                "service ownership or an anycast CDN."
            )
    else:
        lines.append(
            "- No mismatch was produced. Recheck ownership and "
            "CNAME-less anycast cases; the assignment requires at "
            "least one known failure."
        )

    lines.extend([
        "",
        "## Part A packet capture",
        "",
        f"- Delegation response packet: "
        f"{CAPTURE_NOTES['delegation_packet']}",
        f"- Final answer response packet: "
        f"{CAPTURE_NOTES['answer_packet']}",
        f"- Largest response packet: "
        f"{CAPTURE_NOTES['largest_response_packet']}",
        f"- Largest DNS response size: "
        f"{CAPTURE_NOTES['largest_response_bytes']} bytes",
        f"- Why it was large: "
        f"{CAPTURE_NOTES['largest_response_reason']}",
        f"- Matching query packet: {CAPTURE_NOTES['matching_query_packet']}",
        f"- Matching response packet: {CAPTURE_NOTES['matching_response_packet']}",
        f"- Transaction ID: {CAPTURE_NOTES['transaction_id']}",
        "",
    ])

    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    print(f"saved {output_path}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
    "--network",
    default="network-1",
    help="label for the current network, e.g. campus-wifi",
    )
    p.add_argument("--collect", action="store_true")
    p.add_argument("--report", action="store_true")
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.collect:
        collect(a.network)
    elif a.report:
        report()
    else:
        p.print_help()

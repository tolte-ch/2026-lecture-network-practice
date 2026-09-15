# Task 2 DNS and CDN Report

## Measurement environments

- home-wifi: 2026-09-14T13:36:54.625298+00:00
- phone-hotspot: 2026-09-14T13:40:51.619692+00:00

## Classification rule

A site is classified as third-party when the registrable domain of the final CNAME target differs from the registrable domain of the original site. This rule cannot detect a CDN hidden behind A/AAAA anycast records and may confuse two domains owned by the same organization.

## Site table

| site | chain length | final zone | third party? | rule verdict |
|---|---:|---|---|---|
| www.microsoft.com | 2 | akamaiedge.net | yes | yes (correct) |
| www.netflix.com | 1 | netflix.com | no | no (correct) |
| www.adobe.com | 2 | akamai.net | yes | yes (correct) |
| www.cnn.com | 1 | fastly.net | yes | yes (correct) |
| www.apple.com | 3 | akamaiedge.net | yes | yes (correct) |
| www.korea.ac.kr | 0 | korea.ac.kr | no | no (correct) |
| www.stanford.edu | 1 | netlifyglobalcdn.com | yes | yes (correct) |
| www.bbc.co.uk | 2 | fastly.net | yes | yes (correct) |
| www.spotify.com | 1 | fastly.net | yes | yes (correct) |
| www.github.com | 1 | github.com | no | no (correct) |
| www.wikipedia.org | 1 | wikimedia.org | no | yes (wrong) |
| www.nytimes.com | 3 | fastly.net | yes | yes (correct) |

## Steering result

8 of 11 CDN-hosted sites answered with a different non-empty address set when the resolver changed.

Resolver-changed sites: www.microsoft.com, www.adobe.com, www.cnn.com, www.apple.com, www.bbc.co.uk, www.spotify.com, www.github.com, www.nytimes.com

3 of 11 CDN-hosted sites changed for at least one resolver when the network changed.

Network-changed sites: www.microsoft.com, www.adobe.com, www.apple.com

## Known rule failures

- www.wikipedia.org: final target `dyna.wikimedia.org`; manual=no, rule=yes. The domain-name heuristic does not fully represent service ownership or an anycast CDN.

## Part A packet capture

- Delegation response packet: 2
- Final answer response packet: 6
- Largest response packet: 2
- Largest DNS response size: 383 bytes
- Why it was large: The referral response contained multiple NS records and additional glue address records.
- Matching query packet: 5
- Matching response packet: 6
- Transaction ID: 0xd6f3

Task 1 — Iterative DNS Resolution

루트 서버는 www.korea.ac.kr의 A 레코드를 직접 관리하지 않기 때문에 최종 주소 대신 .kr을 담당하는 NS 정보를 반환했다. 구현한 resolver는 루트 서버 198.41.0.4, .kr TLD 서버 210.101.61.1, korea.ac.kr 권한 서버 163.152.11.6 순서로 delegation을 따라가 최종 주소 163.152.6.10을 얻었다.

Delegation에 glue A 레코드가 있으면 그 주소를 다음 질의 대상으로 사용하고, glue가 없으면 NS 호스트 이름의 A 레코드를 루트부터 재귀적으로 해석한 후 그 서버에 질의하도록 구현했다. 또한 CNAME을 만나면 그 대상을 다시 루트부터 해석하고, 무한 반복을 막기 위해 깊이를 제한했다.

www.stanford.edu는 CNAME 대상까지 다시 해석해야 했다. 처음에는 glue가 없는 모든 NS 이름을 미리 해석해 27회 질의했지만, 실제로 사용할 NS만 순차적으로 해석하도록 개선한 뒤 6회로 감소했다.

Task 2 — DNS and CDN Steering

Wireshark에서 패킷 5의 질의와 패킷 6의 응답은 동일한 Transaction ID 0xd6f3을 사용했다. 패킷 2는 Answer count가 0이고 Authority 영역에 .kr의 NS 레코드가 들어 있는 delegation 응답인 반면, 패킷 6은 Answer 영역에 www.korea.ac.kr A 163.152.6.10을 포함한 최종 answer 응답이었다. 가장 큰 응답은 패킷 2의 383-byte 프레임으로, 여러 NS 레코드와 Additional 영역의 glue 주소를 함께 포함했기 때문에 컸다.

제3자 서비스 여부는 원래 이름과 최종 CNAME 대상의 등록 가능 도메인이 다르면 제3자로 분류하는 규칙을 사용했다. 이 규칙은 www.wikipedia.org → dyna.wikimedia.org를 제3자로 판정하지만, 두 도메인은 같은 Wikimedia 조직이 운영하므로 잘못된 판정이다. 이는 도메인 문자열만으로 실제 서비스 소유 관계나 CNAME 없는 anycast CDN을 완전히 판별할 수 없음을 보여 준다.

CDN 사용 대상으로 분류한 11개 사이트 중 8개가 system resolver, Google DNS, Quad9 사이에서 서로 다른 IPv4 주소 집합을 반환했다. 또한 home-wifi와 phone-hotspot을 비교하면 11개 중 3개 사이트인 Adobe, Apple, Microsoft가 적어도 한 리졸버에서 다른 주소 집합을 반환했다. 이는 DNS steering의 존재를 지지하지만, 리졸버 위치·캐시·TTL·round-robin의 영향이 있으므로 반환된 서버가 실제로 가장 가까운 replica라고 단정할 수는 없다.

DNS 패킷에는 사용자가 조회한 도메인 이름이 평문으로 나타날 수 있으므로, 캡처 파일을 공유하기 전에 개인적인 방문 기록이나 민감한 내부 도메인이 포함되지 않았는지 확인해야 한다.

Task 3 — DNS Cache and TTL

BaselineCache의 정확성 문제는 TTL이 20초 또는 30초인 레코드도 60초 동안 보관하여 stale 응답을 반환한다는 것이다. 성능 문제는 TTL이 60초보다 긴 레코드도 60초마다 제거하여 불필요한 upstream 질의를 발생시킨다는 것이다. 두 문제의 공통 원인은 upstream이 반환한 실제 TTL을 무시하는 것이다.

YourCache는 각 항목을 (address, expires_at)으로 저장하고 now < expires_at인 동안에만 재사용하도록 구현했다. 실험 결과 baseline은 upstream 325회, hit rate 67.5%, stale 266개였고, YourCache는 upstream 275회, hit rate 72.5%, stale 0개였다.

이 workload에서 올바른 캐시의 upstream 질의 floor는 275회이다. 각 이름의 첫 요청과 TTL 만료 후의 첫 요청은 반드시 upstream 확인이 필요하며, 이 횟수를 이름별로 합하면 275회가 된다. 그보다 적게 질의하려면 만료된 주소가 여전히 유효하다고 확인하지 않고 반환해야 하므로 stale 응답 가능성이 생긴다.

Baseline이 가장 나쁘게 처리한 레코드는 TTL이 20초인 www.microsoft.com이다. 고정된 60초 보관 정책 때문에 한 번 저장한 뒤 최대 40초 동안 만료된 주소를 반환할 수 있었고, workload에서 가장 자주 요청되어 전체 322회 요청 중 189회의 stale 응답이 발생했다.
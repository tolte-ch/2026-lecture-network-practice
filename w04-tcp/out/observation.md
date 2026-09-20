## Task 1 — Reliable Delivery

Stop-and-wait 프로토콜을 선택했다. 한 번에 하나의 패킷만 전송하고 해당 sequence number의 ACK를 받은 뒤 다음 패킷으로 이동하도록 구현했다. Sliding window보다 느리지만, ACK 손실과 중복 ACK를 구분하기 쉽고 패킷 순서를 단순하게 보장할 수 있다는 점을 선택 이유로 삼았다.

2,000바이트를 8바이트씩 나누므로 손실이 없을 때 필요한 최소 데이터 패킷 수는 250개다. 기본 seed 246에서는 323개를 전송했으므로 최소치의 1.292배, 즉 29.2%의 추가 전송이 필요했다. 다섯 개 seed의 평균 전송량은 311.4개로, 이론적 최소치보다 평균 24.6% 많았다. 모든 seed에서 수신 크기는 2,000바이트였으며 SHA-256 비교 결과는 IDENTICAL이었다.

가장 주의가 필요했던 경우는 duplication이었다. ACK가 손실되면 송신자가 이미 전달된 데이터 패킷을 재전송하므로, 수신자가 sequence number를 검사하지 않으면 같은 payload가 결과에 두 번 추가될 수 있다. 이를 막기 위해 수신자는 expected sequence number와 일치하는 데이터만 추가하고, 이미 처리한 번호가 다시 오면 데이터를 추가하지 않은 채 ACK만 다시 보내도록 구현했다. 송신자도 현재 기다리는 번호와 일치하는 ACK만 인정하여 지연된 중복 ACK가 다음 패킷의 ACK로 처리되지 않게 했다.

## Task 2 — TCP Measurement

### Part A — TCP handshake

Home Wi-Fi에서 발생시킨 HTTPS 다운로드 트래픽을 vEthernet (WSL) 인터페이스에서 직접 캡처했다. 분석한 연결은 TCP stream 0이며, 3-way handshake는 SYN packet 1, SYN-ACK packet 2, ACK packet 3이었다. SYN에서 SYN-ACK까지 약 7.80 ms, 마지막 ACK까지 약 8.36 ms가 걸렸다.

Wireshark의 raw 값을 기준으로 클라이언트 initial sequence number는 3,859,533,628이고 서버 initial sequence number는 672,136,136이었다. 두 값은 서로 다르고 0도 아니었다. 임의의 ISN은 이전 연결에서 지연된 세그먼트가 새로운 연결의 데이터로 오인되는 것을 방지하고 sequence number를 예측하기 어렵게 한다.

클라이언트 SYN의 옵션은 MSS 1460 bytes, window scale shift 10 (multiplier 1024), SACK permitted였다. 서버 SYN-ACK의 옵션은 MSS 1400 bytes, window scale shift 13 (multiplier 8192), SACK permitted였다.

Handshake 직후 packet 3에서 클라이언트의 raw window value는 63이므로 scaled receive window는 63 × 1024 = 64,512 bytes였다. 전송 중 receive-window auto-tuning이 적용되어 packet 399에서는 1,572 × 1,024 = 1,609,728 bytes까지 증가했다. 그 직후 관찰된 최대 bytes in flight는 packet 401의 94,120 bytes로, advertised window의 약 5.85%였다. 따라서 receive window가 주된 제한은 아니었으며, congestion window, slow start, RTT 및 실제 링크 용량이 더 중요한 제한 요인이었다.

### Part B — Throughput

| Network | Five runs (Mbps) | Median | Min–Max | Spread | Median handshake |
| Home Wi-Fi | 66.08, 56.07, 68.72, 70.66, 70.48 | 68.72 Mbps | 56.07–70.66 | 21.2% | 13.563 ms |
| Phone hotspot | 29.87, 39.18, 43.10, 43.72, 44.28 | 43.10 Mbps | 29.87–44.28 | 33.4% | 33.773 ms |

Home Wi-Fi의 처리량 중앙값은 68.72 Mbps이고 Phone hotspot은 43.10 Mbps였다. 핫스팟 처리량은 Wi-Fi의 약 62.7%였으며, spread도 33.4%로 Wi-Fi의 21.2%보다 컸다. 같은 네트워크에서도 결과가 달라진 이유는 무선 채널 경쟁, 신호 상태, 백그라운드 트래픽, 순간적인 큐잉과 서버·네트워크 경로 상태가 매번 달라질 수 있기 때문이다.

Phone hotspot의 첫 번째 실행은 DNS 249.710 ms, handshake 140.844 ms로 다른 실행보다 오래 걸렸으며 처리량도 가장 낮은 29.87 Mbps였다. 이 이상치 때문에 단일 실행보다 다섯 실행의 중앙값이 더 대표적인 측정값이라고 판단했다.

Phone hotspot의 handshake 중앙값은 33.773 ms로 Home Wi-Fi의 13.563 ms보다 약 2.49배 길었고, 처리량 중앙값은 약 37.3% 낮았다. RTT가 길면 ACK 피드백이 늦어지고 TCP slow start에서 congestion window가 증가하는 데 더 많은 시간이 필요하다. 따라서 같은 원시 링크 용량을 가정해도 5 MB처럼 짧은 전송에서는 긴 handshake/RTT가 처리량을 낮출 수 있다. 다만 두 네트워크는 실제 링크 용량과 무선 환경도 다르므로 RTT가 처리량 차이의 유일한 원인이라고 단정할 수는 없다.

## Task 3 — Congestion Control

`YourControl`은 window 1에서 시작하고 ssthresh 20까지 slow start로 증가하도록 구현했다. 이후에는 ACK마다 1/window씩 증가하는 additive increase를 사용하고, 손실이 발생하면 window를 기존 값의 70%로 줄이는 multiplicative decrease를 적용했다.

이 링크의 bandwidth-delay product는 1 packet/slot × RTT 20 slots = 20 packets이다. Window가 20을 넘으면 초과한 패킷이 queue에 쌓이고, 파이프 20패킷과 queue 10패킷이 모두 차는 30 부근에서 tail drop이 발생한다. Window 30에서 70% backoff를 적용하면 약 21이 되므로, 내 알고리즘은 대략 BDP 바로 위에서 drop 경계 사이를 움직이도록 설계했다.

| Sender | Goodput | Loss | Retransmissions | Average queue |
| FixedWindow | 986.8 | 37.4% | 2340 | 8.8 |
| YourControl | 955.2 | 0.5% | 18 | 4.4 |

`YourControl`의 goodput은 baseline의 약 97%로 strong 기준을 충족했다. Loss는 0.5%로 5% 이하였고, 평균 queue도 4.4로 제한 5.0 이하를 유지했다.

Baseline은 goodput이 986.8로 가장 높지만 가장 나쁜 sender이다. Window 64를 유지하여 링크가 수용할 수 있는 약 30패킷보다 훨씬 많이 보내기 때문에 패킷의 37.4%를 버리고 2,340회의 재전송을 발생시킨다. 또한 평균 queue가 8.8/10으로 거의 가득 차 있어 queueing delay를 증가시키고 같은 링크를 공유하는 다른 흐름에도 피해를 준다. 따라서 약간 높은 goodput을 위해 지나치게 많은 손실, 재전송과 지연을 발생시키는 방식은 좋은 혼잡 제어라고 볼 수 없다.

Backoff를 0.50으로 설정했을 때 goodput은 baseline의 87%이고 평균 queue는 3.2였다. Backoff를 0.60으로 완화하자 goodput은 92%, 평균 queue는 3.8이 되었다. 0.70에서는 goodput이 97%까지 증가하면서 평균 queue가 4.4로 제한 안에 유지되었다. 그러나 0.80에서는 goodput이 99%로 증가한 대신 평균 queue가 5.8로 제한을 위반했다. Backoff를 덜 강하게 할수록 처리량은 증가했지만 queueing delay와 재전송도 증가했으므로 최종값으로 0.70을 선택했다.
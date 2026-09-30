# Controlled bench qualification record (blank template)

Use with [the frozen reference](FIELD_TEST_REFERENCE.md) and [the checklist](FIELD_TEST_CHECKLIST_0_1_0.md). Copy this template for each session. An empty field or `NOT RUN` is not evidence of a pass. Never attach live ignition or deployment loads to this software qualification workflow.

## Session identity

- Operator / reviewer: __________ / __________
- Start and end timestamp, including time zone: __________ / __________
- Test location and bench safety procedure: __________
- Flight PCB part, revision, serial: __________
- Ground PCB part, revision, serial: __________
- JY901B / M9N / radio module physical identities: __________
- TF card identity and original log custody path: __________
- Host OS, tools and source commit: __________

## Frozen software identity

Record the actual SHA-256 of all six files and compare each against the reference. Do not substitute a newly built image for a frozen image.

| File | Expected SHA-256 from reference | Observed SHA-256 | Match? |
| --- | --- | --- | --- |
| `SilverStar.ssproject` | __________ | __________ | __________ |
| root `.ssdecoder` | __________ | __________ | __________ |
| Flight `.elf` | __________ | __________ | __________ |
| Flight `.bin` | __________ | __________ | __________ |
| Ground `.elf` | __________ | __________ | __________ |
| Ground `.bin` | __________ | __________ | __________ |

- Frozen project configuration reviewed (100 Hz effective KF6, selected links/resources): __________
- Actual IMU and magnetometer calibration identity/generation readback: __________
- Selected alignment and physical orientation evidence: __________

## Each action

Create one row per applicable checklist action. Record `PASS`, `FAIL`, `NOT RUN`, or `N/A` with a reason for the latter two. For the current KF6 candidate the ESKF15 smoke row is `N/A`, never `PASS`.

| Action / acceptance criterion | Time | Actual observation and measured values | Raw evidence path | Status / reason | Issue and safe recovery |
| --- | --- | --- | --- | --- | --- |
| __________ | __________ | __________ | __________ | __________ | __________ |

## Session decision

- Any unresolved output, START/storage, navigation, link or decoder failure: __________
- Physical evidence completeness and reviewer decision: __________
- Follow-up owner and date: __________
- Reviewer signature/date: __________

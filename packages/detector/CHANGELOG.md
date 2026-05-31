# Changelog

## [0.1.0](https://github.com/f-lab-edu/devopsim/compare/detector-v0.0.5...detector-v0.1.0) (2026-05-31)


### Features

* detector Helm chart + Dockerfile kubectl 추가 ([#94](https://github.com/f-lab-edu/devopsim/issues/94)) ([e27eb71](https://github.com/f-lab-edu/devopsim/commit/e27eb7180ffc1f5465d06e0703d90ad76df7a9d7))
* detector main.py 통합 — build_app + kopf entry + smoke test ([#91](https://github.com/f-lab-edu/devopsim/issues/91)) ([70b2949](https://github.com/f-lab-edu/devopsim/commit/70b2949e5b4ac18aa2b2ac4a20998fa03163e251))
* detector RCA/Slack 한국어 출력 ([#100](https://github.com/f-lab-edu/devopsim/issues/100)) ([567577c](https://github.com/f-lab-edu/devopsim/commit/567577c7a28e983940090cd9feb241ac4c7b5585))
* detector 서비스 골격 + bad-pod-evict 핸들러 (Phase 1 코드) ([4e94acc](https://github.com/f-lab-edu/devopsim/commit/4e94acc154ce8220a03527150a6c27bef108f646))
* detector 서비스 골격 + bad-pod-evict 핸들러 (Phase 1 코드) ([20e423b](https://github.com/f-lab-edu/devopsim/commit/20e423b28c26f238ba091e8c71583a8ef35cc432))
* **detector:** agent loop + Anthropic SDK adapter (B-7) ([d85a307](https://github.com/f-lab-edu/devopsim/commit/d85a30740517aba229ba7c2c777063abf59439c0))
* **detector:** agent loop + Anthropic SDK adapter (TDD 여섯 번째 적용) ([b6ea52c](https://github.com/f-lab-edu/devopsim/commit/b6ea52c6f7f6ba20ae652467f6f38ee6e897b80b))
* **detector:** alertmanager poller trigger ([74f9b5b](https://github.com/f-lab-edu/devopsim/commit/74f9b5bd29065debd029cd1ba7ef8b95f94d2fb3))
* **detector:** alertmanager poller trigger (B-10) ([ecf7c03](https://github.com/f-lab-edu/devopsim/commit/ecf7c039d60391a9abddb16b58f16ffe4899fd09))
* **detector:** alertmanager tool + adapter (B-4) ([1719ae1](https://github.com/f-lab-edu/devopsim/commit/1719ae10c6159698b389358432d62b19a8cbdc21))
* **detector:** alertmanager tool + adapter (TDD 세 번째 적용) ([908af62](https://github.com/f-lab-edu/devopsim/commit/908af62e775cb4ab1a4769cd8a0d641ac0b9dc0e))
* **detector:** annotation trigger ([35a526a](https://github.com/f-lab-edu/devopsim/commit/35a526a6accd48df3f6243e421ca7c4d3888fe89))
* **detector:** annotation trigger (B-11) ([43a0ddc](https://github.com/f-lab-edu/devopsim/commit/43a0ddc92d4125b7a8698574728689a7fb8e51b0))
* **detector:** cluster context + prompt 렌더링 (B-5) ([94e5dca](https://github.com/f-lab-edu/devopsim/commit/94e5dca09f6cb312ae1feb852c585e3827a6e28b))
* **detector:** cluster context + prompt 렌더링 (TDD 네 번째 적용) ([90b97d5](https://github.com/f-lab-edu/devopsim/commit/90b97d59cb4086a297ad5b81558379c0d05c7152))
* **detector:** K8s event watcher trigger ([472835f](https://github.com/f-lab-edu/devopsim/commit/472835f233669b7a51a8b3f9ca903618ee7418a1))
* **detector:** K8s event watcher trigger (B-9) ([1787730](https://github.com/f-lab-edu/devopsim/commit/178773056e13d844c2de9068c58789ad2b0ba50a))
* **detector:** kubectl 도구 4종 + 단위 테스트 + ruff 도입 ([1b60cfd](https://github.com/f-lab-edu/devopsim/commit/1b60cfd3040dcf742c18e05df949a3f0412a3d95))
* **detector:** kubectl 도구 4종 + 어댑터 ([a8e3dae](https://github.com/f-lab-edu/devopsim/commit/a8e3dae3abc7aaf0d0cacb85c12d6b0e7746377f))
* **detector:** loki tool + adapter (B-3b) ([eda02d7](https://github.com/f-lab-edu/devopsim/commit/eda02d73f4b23a11e58fb87665ff935370f25be4))
* **detector:** loki tool + adapter (TDD 두 번째 적용) ([be11b2f](https://github.com/f-lab-edu/devopsim/commit/be11b2fcb104b489a5b951ae38cca9a9ca29c37d))
* **detector:** metrics — Prometheus instrumentation ([0f84c7c](https://github.com/f-lab-edu/devopsim/commit/0f84c7ce7f264118f23e81bd22a809c254473788))
* **detector:** metrics — Prometheus instrumentation (B-12) ([8e9a91b](https://github.com/f-lab-edu/devopsim/commit/8e9a91b125c25090400801201c7b88056c9772cd))
* **detector:** promql tool + adapter (TDD 첫 적용) ([f1c3d9d](https://github.com/f-lab-edu/devopsim/commit/f1c3d9d395d1e4b6b54120c1c1b2547d224390ba))
* **detector:** remediation tools — Phase B 마지막 (B-13) ([e9df19c](https://github.com/f-lab-edu/devopsim/commit/e9df19c1b57bc6ca7441110276ead6f81f8bae35))
* **detector:** remediation tools (restart/scale/delete with safety guards) ([0148e20](https://github.com/f-lab-edu/devopsim/commit/0148e20807209e14c9a01b65ef55041e915e324f))
* **detector:** runbook system + 콘텐츠 (B-6) ([ed9ad94](https://github.com/f-lab-edu/devopsim/commit/ed9ad9461f2aa7c28d62d987143fc925d8b0a79e))
* **detector:** runbook system + 콘텐츠 (TDD 다섯 번째 적용) ([9edfaf8](https://github.com/f-lab-edu/devopsim/commit/9edfaf80493c5d6a728e3d89880297f61ebbdbb9))
* **detector:** slack destination (B-8) ([a9750f2](https://github.com/f-lab-edu/devopsim/commit/a9750f237f4574e04ccb51fea83f1cada5b80528))
* **detector:** slack destination (TDD 일곱 번째 적용) ([8547412](https://github.com/f-lab-edu/devopsim/commit/8547412b4fbd20dfb3e98c0c1acd706717583ddb))
* **detector:** tool 베이스 (pydantic input + 비동기 핸들러) ([10d2b02](https://github.com/f-lab-edu/devopsim/commit/10d2b02e24b5ffa3ec61984054af29004ff31eee))
* TDD 인프라(/spec, /tdd) + 첫 적용 — promql tool ([1afa810](https://github.com/f-lab-edu/devopsim/commit/1afa8103f30541cb9979d8d9f55f2976a6133e80))


### Bug Fixes

* detector annotation 트리거 + investigate 진단 로깅 ([#98](https://github.com/f-lab-edu/devopsim/issues/98)) ([b674d99](https://github.com/f-lab-edu/devopsim/commit/b674d99d53e3d3464cae55350e7d3b7f908ba59b))
* detector LLM 빈 text 블록 필터링 + API 에러 본문 로깅 ([#97](https://github.com/f-lab-edu/devopsim/issues/97)) ([93ed5c8](https://github.com/f-lab-edu/devopsim/commit/93ed5c8ffafa3db0bb934d74ac53d4db2f90acb5))
* detector parallel tool_use 비활성화 ([#99](https://github.com/f-lab-edu/devopsim/issues/99)) ([ec0c763](https://github.com/f-lab-edu/devopsim/commit/ec0c76368449b5e9a0a7d6b0cd620ccb574dfbdc))

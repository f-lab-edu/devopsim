# Changelog

## [0.9.1](https://github.com/f-lab-edu/devopsim/compare/api-v0.9.0...api-v0.9.1) (2026-05-05)


### Bug Fixes

* HTTP 메트릭 hook을 fastify-plugin으로 hoist ([ce7f096](https://github.com/f-lab-edu/devopsim/commit/ce7f096bbdaa8e788ef41efc4c1119fa1a4426a6))
* HTTP 메트릭 hook을 fastify-plugin으로 hoist — /metrics 외 라우트도 수집 ([ae7f522](https://github.com/f-lab-edu/devopsim/commit/ae7f5226aa4a61c933b37a3335b443ad6a373339))

## [0.9.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.8.0...api-v0.9.0) (2026-05-05)


### Features

* chaos 엔드포인트에 cache/db 시뮬레이션 추가 ([69f6c1e](https://github.com/f-lab-edu/devopsim/commit/69f6c1e1d54e9068ef0370c81c5b61c71fbb04cd))
* chaos 엔드포인트에 cache/db 시뮬레이션 추가 ([e5f19b3](https://github.com/f-lab-edu/devopsim/commit/e5f19b3d8004a65d09a46d3776208612460c483c))

## [0.8.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.7.0...api-v0.8.0) (2026-05-05)


### Features

* custom Prometheus 메트릭 추가 + 디렉토리 구조 정리 ([b95e256](https://github.com/f-lab-edu/devopsim/commit/b95e256cd8d2d361a2c70b965c51be00ecb57814))
* custom Prometheus 메트릭 추가 + 디렉토리 구조 정리 ([07e0157](https://github.com/f-lab-edu/devopsim/commit/07e0157d455ab88f73a1f49aff63ec57b47bca54))


### Bug Fixes

* gauge factory를 idempotent하게 — 테스트 중복 등록 회피 ([f45f553](https://github.com/f-lab-edu/devopsim/commit/f45f5535c908cc88de62843df27abb390facadce))

## [0.7.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.6.0...api-v0.7.0) (2026-05-05)


### Features

* Redis 캐시 레이어 추가 ([8343d91](https://github.com/f-lab-edu/devopsim/commit/8343d91396a13ab5df3013a98416f63b3c75a624))
* Redis 캐시 레이어 추가 + api 네임스페이스 이동 ([10cf475](https://github.com/f-lab-edu/devopsim/commit/10cf475bbf9760f5e953fc0a50458e40637eab46))

## [0.6.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.5.0...api-v0.6.0) (2026-04-27)


### Features

* add GET /api/items/popular endpoint ([52397f2](https://github.com/f-lab-edu/devopsim/commit/52397f21c07b97ccb557bd6596a7c78121de438f))
* topologySpread + Karpenter/HPA docs ([a2fc361](https://github.com/f-lab-edu/devopsim/commit/a2fc36188af638e1b3728bf5e84f3238a6d61399))

## [0.5.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.4.0...api-v0.5.0) (2026-04-27)


### Features

* add /chaos/cpu endpoint for load testing ([0fe41b9](https://github.com/f-lab-edu/devopsim/commit/0fe41b923529bc587d68778dbca5235d65e13b41))
* introduce Karpenter for autoscaling ([e3477ef](https://github.com/f-lab-edu/devopsim/commit/e3477ef1c7b0b45fea54763d103f00683037fa49))

## [0.4.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.3.0...api-v0.4.0) (2026-04-26)


### Features

* increment view_count on GET /api/items/:id ([5e7673b](https://github.com/f-lab-edu/devopsim/commit/5e7673bd5c795a69a6531b25e36822336d95d99f))
* increment view_count on GET /api/items/:id ([38d93cc](https://github.com/f-lab-edu/devopsim/commit/38d93cc84bcef45a3f94d58aaa21235006832ae2))

## [0.3.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.2.2...api-v0.3.0) (2026-04-21)


### Features

* add pagination to GET /api/items ([a8d60b6](https://github.com/f-lab-edu/devopsim/commit/a8d60b632764fd8a34122bfaaeda7ac4bec22d25))
* add pagination to GET /api/items ([6289085](https://github.com/f-lab-edu/devopsim/commit/62890850e66c2cb3bd829b20fae86ea2521bd764))

## [0.2.2](https://github.com/f-lab-edu/devopsim/compare/api-v0.2.1...api-v0.2.2) (2026-04-20)


### Bug Fixes

* return integer uptime in health endpoint ([2607900](https://github.com/f-lab-edu/devopsim/commit/2607900fdde6aaf73d4a3ace89751bd4fe295c52))
* use Math.round for uptime ([b6c9862](https://github.com/f-lab-edu/devopsim/commit/b6c98625972f0e7be62465baf82d31dd1598dd29))

## [0.2.1](https://github.com/f-lab-edu/devopsim/compare/api-v0.2.0...api-v0.2.1) (2026-04-20)


### Bug Fixes

* add uptime to health endpoint ([5b608ff](https://github.com/f-lab-edu/devopsim/commit/5b608ffa4bc549edbdd2c283ac6c918d7c252c99))

## [0.2.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.1.2...api-v0.2.0) (2026-04-20)


### Features

* add /metrics endpoint with HTTP and DB pool metrics ([be978b5](https://github.com/f-lab-edu/devopsim/commit/be978b5cfa52d2522027ee7dd218d098c682924e))

## [0.1.2](https://github.com/f-lab-edu/devopsim/compare/api-v0.1.1...api-v0.1.2) (2026-04-20)


### Bug Fixes

* add APP_SERVICE build arg to Dockerfile and ci.yaml ([cfff7f9](https://github.com/f-lab-edu/devopsim/commit/cfff7f969aef0739d154e66c3369096b62d4afc9))

## [0.1.1](https://github.com/f-lab-edu/devopsim/compare/api-v0.1.0...api-v0.1.1) (2026-04-20)


### Bug Fixes

* add APP_SERVICE env var to version endpoint ([89ab4b2](https://github.com/f-lab-edu/devopsim/commit/89ab4b2cc99eed671b0fe387e6e29a0982357df6))

## [0.1.0](https://github.com/f-lab-edu/devopsim/compare/api-v0.0.1...api-v0.1.0) (2026-04-20)


### Features

* add /api/version endpoint ([6b0be77](https://github.com/f-lab-edu/devopsim/commit/6b0be777fc259c9419dbe28a838957caa0e5af57))
* add /ready endpoint with DB health check ([61ce4e5](https://github.com/f-lab-edu/devopsim/commit/61ce4e5c59b07b85d93d53f1d32372dd4c2de8f8))
* add Dockerfile naive and optimized versions ([dda8702](https://github.com/f-lab-edu/devopsim/commit/dda870205bf784f6a9bb6f9362ef3e267a1ca58f))
* add domain layer and repository pattern ([4ee8163](https://github.com/f-lab-edu/devopsim/commit/4ee81638b1c20e49167a29adc50e67b08e596ec7))
* add health endpoint with base project structure ([cce8c8b](https://github.com/f-lab-edu/devopsim/commit/cce8c8bf302c9f062410518bf6c5f66b24a0ddfd))
* add items CRUD routes with schema validation ([c6617ac](https://github.com/f-lab-edu/devopsim/commit/c6617ac7006bc5e99fa64dafe47d3bfef4cac959))
* add items table migration ([c9b3897](https://github.com/f-lab-edu/devopsim/commit/c9b3897b287d2a8c2cadd4b1b0960954e46cf2d3))
* add PostgreSQL connection plugin ([0da7901](https://github.com/f-lab-edu/devopsim/commit/0da79012f68121a274ddbb1a1439ab5066de2e94))
* add release workflow, release-please, and /version build metadata ([b74561c](https://github.com/f-lab-edu/devopsim/commit/b74561c762ed079c66617b89c0e842837d94de72))
* add Service, Ingress and /api prefix to items routes ([3ccbc56](https://github.com/f-lab-edu/devopsim/commit/3ccbc5667fbd30661b38d3b8694eca91f62bff5e))
* integrate shared logger and HealthResponse into api ([24e0bb5](https://github.com/f-lab-edu/devopsim/commit/24e0bb523d0b6b15d1c15cc1b2a5bede9c9db411))
* optimize Dockerfile with 3-stage build ([6da225c](https://github.com/f-lab-edu/devopsim/commit/6da225cb868191501d5933ec8835eaea4c951952))
* replace psql migration with node-pg-migrate ([b5ff3b1](https://github.com/f-lab-edu/devopsim/commit/b5ff3b166a4461d8dba6bd5e549569b59eec5af8))

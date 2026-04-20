# Changelog

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

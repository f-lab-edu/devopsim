import os
from dataclasses import dataclass

PROMETHEUS_DEFAULT = "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"
LOKI_DEFAULT = "http://loki.monitoring.svc.cluster.local:3100"
ALERTMANAGER_DEFAULT = "http://kube-prometheus-stack-alertmanager.monitoring.svc.cluster.local:9093"
MODEL_DEFAULT = "claude-sonnet-4-6"


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    model: str
    prometheus_url: str
    loki_url: str
    alertmanager_url: str
    slack_webhook_url: str
    allowed_namespaces: tuple[str, ...]
    max_steps: int
    dry_run: bool

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            model=os.environ.get("DETECTOR_MODEL", MODEL_DEFAULT),
            prometheus_url=os.environ.get("PROMETHEUS_URL", PROMETHEUS_DEFAULT),
            loki_url=os.environ.get("LOKI_URL", LOKI_DEFAULT),
            alertmanager_url=os.environ.get("ALERTMANAGER_URL", ALERTMANAGER_DEFAULT),
            slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL", ""),
            allowed_namespaces=tuple(
                ns.strip() for ns in os.environ.get("ALLOWED_NAMESPACES", "api").split(",") if ns.strip()
            ),
            max_steps=int(os.environ.get("MAX_STEPS", "10")),
            dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
        )

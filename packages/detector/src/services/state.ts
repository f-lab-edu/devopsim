export interface ActionRecord {
  alertname: string
  action: string
  target: string  // 예: pod 이름
  at: number      // epoch ms
}

// 같은 fingerprint(alertname + label set)당 마지막 액션을 저장 + 같은 target에 대한 cool-down 추적.
// in-memory Map — detector 재시작 시 휘발. Phase 1 학습용으로 충분.
// 분산 환경(replicas>1)에서는 Redis 필요하지만 detector는 replicas=1 운영.
export class ActionStore {
  private byFingerprint = new Map<string, ActionRecord>()
  private byTarget = new Map<string, number>()

  recordAction(fingerprint: string, record: ActionRecord) {
    this.byFingerprint.set(fingerprint, record)
    this.byTarget.set(record.target, record.at)
  }

  // target이 최근 cool-down 안에 액션 받았는지 확인
  isOnCoolDown(target: string, coolDownMs: number, now: number = Date.now()): boolean {
    const last = this.byTarget.get(target)
    if (!last) return false
    return now - last < coolDownMs
  }

  forgetFingerprint(fingerprint: string) {
    this.byFingerprint.delete(fingerprint)
  }

  activeCount(): number {
    return this.byFingerprint.size
  }
}

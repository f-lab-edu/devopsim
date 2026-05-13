export interface PromSample {
  metric: Record<string, string>
  value: number
}

export interface PrometheusClient {
  query(promql: string): Promise<PromSample[]>
}

export function createPrometheusClient(baseUrl: string): PrometheusClient {
  return {
    async query(promql) {
      const url = new URL('/api/v1/query', baseUrl)
      url.searchParams.set('query', promql)
      const res = await fetch(url, { signal: AbortSignal.timeout(5000) })
      if (!res.ok) {
        throw new Error(`prometheus query failed: ${res.status} ${res.statusText}`)
      }
      const json = (await res.json()) as {
        status: string
        data?: { resultType: string; result: Array<{ metric: Record<string, string>; value: [number, string] }> }
        error?: string
      }
      if (json.status !== 'success') {
        throw new Error(`prometheus query error: ${json.error ?? 'unknown'}`)
      }
      return (json.data?.result ?? []).map((r) => ({
        metric: r.metric,
        value: Number(r.value[1]),
      }))
    },
  }
}

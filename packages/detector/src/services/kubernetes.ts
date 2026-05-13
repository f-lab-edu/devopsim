import * as k8s from '@kubernetes/client-node'

export interface KubernetesClient {
  listPods(namespace: string, labelSelector: string): Promise<string[]>
  deletePod(namespace: string, name: string): Promise<void>
  getDeploymentMinReplicas(namespace: string, name: string): Promise<number>
}

export function createKubernetesClient(): KubernetesClient {
  const kc = new k8s.KubeConfig()
  // in-cluster ServiceAccount JWT 우선, 로컬 dev 시 ~/.kube/config fallback
  try {
    kc.loadFromCluster()
  } catch {
    kc.loadFromDefault()
  }

  const core = kc.makeApiClient(k8s.CoreV1Api)
  const apps = kc.makeApiClient(k8s.AppsV1Api)

  return {
    async listPods(namespace, labelSelector) {
      const res = await core.listNamespacedPod({ namespace, labelSelector })
      return res.items.map((p) => p.metadata?.name ?? '').filter(Boolean)
    },

    async deletePod(namespace, name) {
      await core.deleteNamespacedPod({ namespace, name })
    },

    async getDeploymentMinReplicas(namespace, name) {
      const res = await apps.readNamespacedDeployment({ namespace, name })
      return res.spec?.replicas ?? 1
    },
  }
}

# Kubernetes Starter Production Setup

This folder provides a starter deployment for this app with two deployment modes:

- `overlays/staging`: standard rolling updates with `Deployment`
- `overlays/prod`: blue/green deployment with Argo Rollouts

## Prerequisites

- Kubernetes cluster (1.27+ recommended)
- Ingress controller (NGINX assumed)
- cert-manager with a `ClusterIssuer` named `letsencrypt-prod`
- Storage classes for PVCs (`ReadWriteMany` for shared app data recommended)
- Argo Rollouts controller (for prod overlay)

## Images and secrets

1. Build and push your app image from CI.
2. Update image name/tag or digest in overlay `kustomization.yaml`.
3. Update `secret.yaml` in each overlay with real values.
4. Do not commit real secrets. Prefer External Secrets / Sealed Secrets.

## Deploy staging (rolling)

```bash
kubectl apply -k k8s/overlays/staging
kubectl -n rag-chatbot get pods
kubectl -n rag-chatbot rollout status deploy/rag-chatbot-app
```

## Deploy production (blue/green)

```bash
kubectl apply -k k8s/overlays/prod
kubectl -n rag-chatbot get rollouts
kubectl -n rag-chatbot argo rollouts get rollout rag-chatbot-app
```

Promote preview to active:

```bash
kubectl -n rag-chatbot argo rollouts promote rag-chatbot-app
```

Abort and rollback current rollout:

```bash
kubectl -n rag-chatbot argo rollouts abort rag-chatbot-app
```

## Notes for this application

- `app` and `worker` share `/data` for embeddings/uploads/logs; this requires storage that supports shared access in multi-node clusters.
- `redis` hostname is `redis` and `ollama` hostname is `ollama`, matching code defaults.
- Ingress host defaults:
  - staging: `rag-staging.example.com`
  - prod: `rag.example.com`

## Recommended hardening next

- Replace in-app hardcoded session secret with env-based secret.
- Add NetworkPolicies.
- Add Pod anti-affinity and topology spread constraints.
- Add Prometheus scraping and alerts.
- Move secrets to External Secrets + cloud KMS.

# Production DNS for Arena Public Access

Eliminates the Cloudflare Quick Tunnel entirely by making
`*.apps.arena.fm2aihpcsed.com` publicly resolvable with a browser-trusted
wildcard TLS certificate.

## Prerequisites

These are external infrastructure steps that must happen outside the cluster:

### 1. Public DNS Zone

The domain `fm2aihpcsed.com` (or a delegated subdomain like
`arena.fm2aihpcsed.com`) needs a public DNS zone with a provider supported
by cert-manager's DNS01 solver.  Supported providers include:

- **Cloudflare** (free tier works)
- Route53
- Google Cloud DNS
- Azure DNS

Create a wildcard A or CNAME record:

```
*.apps.arena.fm2aihpcsed.com → <public-ip-of-router>
```

### 2. External Router Access

Arena's router (`router-internal-default`) is currently ClusterIP-only on
private `192.168.1.x` addresses. Options to expose it:

- **Reverse proxy / jump host:** An external host with a public IP that
  forwards TCP 443 to the router pod IP (simplest for lab environments)
- **MetalLB:** Deploy MetalLB and allocate a public IP pool
- **NodePort + firewall rule:** Change the IngressController to NodePort and
  open the port on the network firewall

### 3. DNS Provider API Credentials

For Let's Encrypt wildcard certificates, cert-manager uses DNS01 challenges.
Create a Kubernetes Secret with the DNS provider API credentials.

**Cloudflare example** (edit and apply `dns-credentials.yaml`):

```sh
# Create from your Cloudflare API token:
oc create secret generic cloudflare-api-token \
  -n cert-manager \
  --from-literal=api-token=<YOUR-CLOUDFLARE-API-TOKEN>
```

## Deployment

Once the three prerequisites are met:

```sh
# 1. Create the DNS provider credentials secret (see above)

# 2. Edit cluster-issuer.yaml if not using Cloudflare
#    (change the dns01 solver section)

# 3. Apply the ClusterIssuer
KUBECONFIG=.arena-kubeconfig oc apply -f deploy/prod-dns/cluster-issuer.yaml

# 4. Apply the wildcard Certificate
KUBECONFIG=.arena-kubeconfig oc apply -f deploy/prod-dns/wildcard-cert.yaml

# 5. Wait for cert to be ready
KUBECONFIG=.arena-kubeconfig oc get certificate -n openshift-ingress -w

# 6. Patch the IngressController to use the new cert
KUBECONFIG=.arena-kubeconfig oc apply -f deploy/prod-dns/ingress-patch.yaml

# 7. Update clusters.yaml
#    Set public_access_enabled: true and remove the tunnel config
```

## What This Gives You

- `*.apps.arena.fm2aihpcsed.com` resolves publicly and has a Let's Encrypt
  wildcard cert
- Showroom, Console, and OAuth all share the same `*.apps.arena` origin
- No SameSite cookie issues, no CSP/XFO rewrites, no port-forwards
- No cloudflared, no local router, no tunnel hostname propagation
- The `deploy/console-embed/` playbook handles the remaining `frame-ancestors`
  for Showroom-in-Console embedding

## Rollback

```sh
# Remove the cert and let the ingress operator generate a new self-signed one
KUBECONFIG=.arena-kubeconfig oc delete certificate arena-wildcard -n openshift-ingress
KUBECONFIG=.arena-kubeconfig oc patch ingresscontroller default -n openshift-ingress-operator \
  --type=json -p '[{"op":"remove","path":"/spec/defaultCertificate"}]'
```

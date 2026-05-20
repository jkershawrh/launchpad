{{- define "launchpad-demo.namespace" -}}
{{ .Values.demo.namespace | default (printf "user-%s-demo" .Values.tenant.name) }}
{{- end -}}

{{- define "launchpad-demo.labels" -}}
app.kubernetes.io/part-of: launchpad
app.kubernetes.io/managed-by: argocd
launchpad.redhat.com/tenant: {{ .Values.tenant.name }}
{{- end -}}

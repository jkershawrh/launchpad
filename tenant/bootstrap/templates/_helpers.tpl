{{- define "launchpad-demo.namespace" -}}
{{ .Values.demo.namespace | default (printf "user-%s-demo" .Values.tenant.name) }}
{{- end -}}

{{- define "launchpad-demo.labels" -}}
app.kubernetes.io/part-of: launchpad
app.kubernetes.io/managed-by: {{ .Values.managedBy | default "argocd" }}
launchpad.redhat.com/tenant: {{ .Values.tenant.name }}
{{- if .Values.sessionId }}
launchpad.redhat.com/session-id: {{ .Values.sessionId }}
{{- end }}
launchpad.redhat.com/catalog-item: {{ .Values.demo.catalogItem | default "unknown" }}
launchpad.redhat.com/purpose: {{ .Values.demo.purpose | default "self-service" }}
{{- if .Values.workshopId }}
launchpad.redhat.com/workshop-id: {{ .Values.workshopId }}
{{- end }}
{{- if .Values.demo.persistence }}
launchpad.redhat.com/persistence: {{ .Values.demo.persistence }}
{{- end }}
{{- end -}}

{{- define "launchpad-demo.selectorLabels" -}}
app.kubernetes.io/part-of: launchpad
launchpad.redhat.com/tenant: {{ .Values.tenant.name }}
{{- end -}}

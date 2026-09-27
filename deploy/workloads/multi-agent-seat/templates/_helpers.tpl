{{- define "multiAgent.runtimeSecret" -}}
{{- required "runtime.existingSecret is required" .Values.runtime.existingSecret -}}
{{- end -}}

{{- define "multiAgent.image" -}}
{{- $repository := required "image.repository is required" .Values.image.repository -}}
{{- $digest := required "image.digest is required" .Values.image.digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail "image.digest must be an immutable sha256 digest" -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- end -}}

{{- define "multiAgent.presentationImage" -}}
{{- $repository := required "presentation.image.repository is required" .Values.presentation.image.repository -}}
{{- $digest := required "presentation.image.digest is required" .Values.presentation.image.digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail "presentation.image.digest must be an immutable sha256 digest" -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- end -}}

{{- define "multiAgent.selectorLabels" -}}
app.kubernetes.io/name: multi-agent-seat
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}

{{- define "multiAgent.labels" -}}
{{ include "multiAgent.selectorLabels" . }}
app.kubernetes.io/managed-by: launchpad
app.kubernetes.io/part-of: multi-agent-quickstart
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
launchpad.redhat.com/session-id: {{ required "identity.sessionId is required" .Values.identity.sessionId | quote }}
launchpad.redhat.com/workshop-id: {{ required "identity.workshopId is required" .Values.identity.workshopId | quote }}
launchpad.redhat.com/seat-id: {{ required "identity.seatId is required" .Values.identity.seatId | quote }}
launchpad.redhat.com/tenant: {{ required "identity.tenantId is required" .Values.identity.tenantId | quote }}
launchpad.redhat.com/cluster-id: {{ required "identity.clusterId is required" .Values.identity.clusterId | quote }}
{{- end -}}

{{- define "multiAgent.presentationSelectorLabels" -}}
app.kubernetes.io/name: agentic-operations-presentation
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}

{{- define "multiAgent.presentationLabels" -}}
{{ include "multiAgent.presentationSelectorLabels" . }}
app.kubernetes.io/managed-by: launchpad
app.kubernetes.io/part-of: multi-agent-quickstart
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
launchpad.redhat.com/session-id: {{ required "identity.sessionId is required" .Values.identity.sessionId | quote }}
launchpad.redhat.com/workshop-id: {{ required "identity.workshopId is required" .Values.identity.workshopId | quote }}
launchpad.redhat.com/seat-id: {{ required "identity.seatId is required" .Values.identity.seatId | quote }}
launchpad.redhat.com/tenant: {{ required "identity.tenantId is required" .Values.identity.tenantId | quote }}
launchpad.redhat.com/cluster-id: {{ required "identity.clusterId is required" .Values.identity.clusterId | quote }}
{{- end -}}

{{- define "multiAgent.containerSecurityContext" -}}
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
readOnlyRootFilesystem: true
runAsNonRoot: true
{{- end -}}

{{- define "multiAgent.modelEnv" -}}
- name: MODEL_ENDPOINT
  valueFrom:
    secretKeyRef:
      name: {{ include "multiAgent.runtimeSecret" . }}
      key: MODEL_ENDPOINT
- name: MODEL_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "multiAgent.runtimeSecret" . }}
      key: MODEL_API_KEY
- name: MODEL_NAME
  valueFrom:
    secretKeyRef:
      name: {{ include "multiAgent.runtimeSecret" . }}
      key: MODEL_NAME
- name: AGENT_AUTH_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "multiAgent.runtimeSecret" . }}
      key: AGENT_AUTH_TOKEN
{{- end -}}

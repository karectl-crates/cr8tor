{{- define "cr8tor-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Setting the operator name
*/}}
{{- define "cr8tor-operator.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Setup chart name and version
*/}}
{{- define "cr8tor-operator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Labels for deployment and pods
*/}}
{{- define "cr8tor-operator.labels" -}}
helm.sh/chart: {{ include "cr8tor-operator.chart" . }}
{{ include "cr8tor-operator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: operator
app.kubernetes.io/part-of: karectl
{{- end }}
{{/*
Selector labels
*/}}
{{- define "cr8tor-operator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "cr8tor-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Assign the service account name
*/}}
{{- define "cr8tor-operator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "cr8tor-operator.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the image name
*/}}
{{- define "cr8tor-operator.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag }}
{{- printf "%s/%s:%s" .Values.image.registry .Values.image.repository $tag }}
{{- end }}

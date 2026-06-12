// API Management — the governed AI gateway in front of the backend/Foundry.
// This scaffolds the service, a backend, the API, and the chat operation.
// Apply the full policy from apim/policies/chat-operation.policy.xml after
// configuring Named Values (see apim/policies/README.md).
metadata description = 'API Management service, API, and chat operation for the County Assistant AI gateway.'

@description('Azure region.')
param location string

@description('API Management service name.')
param name string

@description('Publisher email (required by API Management).')
param publisherEmail string

@description('Publisher organization name.')
param publisherName string

@description('APIM SKU name. Use Developer for non-prod; StandardV2/Premium for prod.')
@allowed([
  'Developer'
  'Basic'
  'Standard'
  'StandardV2'
  'Premium'
])
param skuName string = 'Developer'

@description('APIM scale units.')
param skuCapacity int = 1

@description('Backend URL the gateway routes to. Per the reference architecture this is the FastAPI orchestrator (Container App) which in turn calls Foundry + Azure AI Search. Falls back to the Foundry account endpoint only when the backend is not deployed.')
param backendUrl string

@description('Application Insights connection string for gateway diagnostics.')
param appInsightsConnectionString string = ''

@description('Log Analytics workspace resource ID for gateway diagnostic logs (ApiManagementGatewayLogs / "GatewayLogs" table). Leave empty to skip.')
param logAnalyticsId string = ''

@description('Resource tags.')
param tags object = {}

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    capacity: skuCapacity
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

resource backend 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'assistant-backend'
  properties: {
    protocol: 'http'
    url: backendUrl
  }
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'county-assistant'
  properties: {
    displayName: 'County Assistant'
    path: 'assistant'
    protocols: [
      'https'
    ]
    subscriptionRequired: true
  }
}

resource chatOperation 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'chat'
  properties: {
    displayName: 'Chat'
    method: 'POST'
    urlTemplate: '/chat'
    responses: [
      {
        statusCode: 200
        description: 'Chat response'
      }
    ]
  }
}

// Application Insights logger for gateway diagnostics (request/dependency traces).
resource apimLogger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = if (!empty(appInsightsConnectionString)) {
  parent: apim
  name: 'appinsights'
  properties: {
    loggerType: 'applicationInsights'
    description: 'County Assistant gateway telemetry'
    credentials: {
      connectionString: appInsightsConnectionString
    }
  }
}

// Platform diagnostic settings -> Log Analytics. This is what surfaces the
// ApiManagementGatewayLogs ("GatewayLogs") table in the APIM Logs blade. Without
// this, no gateway request rows are ever written to Log Analytics.
resource apimDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsId)) {
  name: 'apim-to-law'
  scope: apim
  properties: {
    workspaceId: logAnalyticsId
    logs: [
      {
        category: 'GatewayLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

output name string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
output principalId string = apim.identity.principalId

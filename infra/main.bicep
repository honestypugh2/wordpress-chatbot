// =============================================================================
// County Assistant — Azure intelligence layer (resource-group scoped).
//
// Composes: managed identity, observability, Key Vault, Azure AI Search,
// Azure AI Foundry (account + project + model), API Management gateway, and the
// backend orchestrator host — Azure Functions (default) or Container Apps.
//
// Deploy:
//   az group create -n rg-county-assistant -l eastus2
//   az deployment group create \
//     -g rg-county-assistant \
//     -f infra/main.bicep \
//     -p infra/main.bicepparam
//
// NOTE: API versions and model availability vary by region — verify before
// deploying to production.
// =============================================================================

targetScope = 'resourceGroup'

@description('Base name used to derive resource names (lowercase, 3-12 chars).')
@minLength(3)
@maxLength(12)
param namePrefix string = 'wpcounty'

@description('Deployment environment moniker.')
@allowed([
  'dev'
  'test'
  'prod'
])
param environmentName string = 'dev'

@description('Primary Azure region.')
param location string = resourceGroup().location

@description('APIM publisher email (required by API Management).')
param apimPublisherEmail string

@description('APIM publisher organization name.')
param apimPublisherName string = 'County of Westvale'

@description('APIM SKU. Developer for non-prod; StandardV2/Premium for prod.')
@allowed([
  'Developer'
  'Basic'
  'Standard'
  'StandardV2'
  'Premium'
])
param apimSku string = 'Developer'

@description('Azure AI Search SKU.')
@allowed([
  'basic'
  'standard'
  'standard2'
  'standard3'
])
param searchSku string = 'basic'

@description('''Optional principal ID granted Search Index Data Contributor for
ingestion (running scripts/index_kb_to_search.py). Leave empty to skip. Typically
the developer/CI object ID; the runtime managed identity stays read-only.''')
param searchIndexAdminPrincipalId string = ''

@description('Principal type for searchIndexAdminPrincipalId (User for a developer, ServicePrincipal for CI/MI).')
@allowed([
  'User'
  'ServicePrincipal'
])
param searchIndexAdminPrincipalType string = 'User'

@description('Foundry model to deploy.')
param modelName string = 'gpt-4o-mini'

@description('Foundry model version.')
param modelVersion string = '2024-07-18'

@description('Model deployment capacity (thousands of tokens per minute).')
param modelCapacity int = 20

@description('''Which compute hosts the backend orchestrator:
- function     → Azure Functions (Flex Consumption). Serverless, scale-to-zero. DEFAULT / recommended.
- containerapp → Azure Container Apps (always-on FastAPI). Portable alternative for demonstration.
- none         → Deploy no backend (APIM falls back to the raw Foundry endpoint; chat contract will not match).''')
@allowed([
  'function'
  'containerapp'
  'none'
])
param backendHost string = 'function'

@description('Backend container image for the Container Apps option (build & push before selecting containerapp).')
param backendImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

var deployFunction = backendHost == 'function'
var deployContainerApp = backendHost == 'containerapp'

// ----------------------------------------------------------------------------
// Naming
// ----------------------------------------------------------------------------
var suffix = uniqueString(resourceGroup().id, namePrefix, environmentName)
var shortSuffix = take(suffix, 6)
var baseName = '${namePrefix}-${environmentName}'
var searchIndexName = 'county-kb'
var tags = {
  application: 'county-assistant'
  environment: environmentName
  workload: 'wordpress-chatbot'
}

// ----------------------------------------------------------------------------
// Modules
// ----------------------------------------------------------------------------
module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    location: location
    name: '${baseName}-id'
    tags: tags
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    logAnalyticsName: '${baseName}-law'
    appInsightsName: '${baseName}-appi'
    tags: tags
  }
}

module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    name: take('kv${replace(suffix, '-', '')}', 24)
    principalId: identity.outputs.principalId
    tags: tags
  }
}

module search 'modules/search.bicep' = {
  name: 'search'
  params: {
    location: location
    name: toLower('${baseName}-search-${shortSuffix}')
    principalId: identity.outputs.principalId
    sku: searchSku
    indexAdminPrincipalId: searchIndexAdminPrincipalId
    indexAdminPrincipalType: searchIndexAdminPrincipalType
    tags: tags
  }
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  params: {
    location: location
    accountName: toLower('${baseName}-aifoundry-${shortSuffix}')
    projectName: 'county-assistant'
    principalId: identity.outputs.principalId
    modelName: modelName
    modelVersion: modelVersion
    modelCapacity: modelCapacity
    logAnalyticsId: monitoring.outputs.logAnalyticsId
    appInsightsId: monitoring.outputs.appInsightsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    tags: tags
  }
}

module apim 'modules/apim.bicep' = {
  name: 'apim'
  params: {
    location: location
    name: toLower('${baseName}-apim-${shortSuffix}')
    publisherEmail: apimPublisherEmail
    publisherName: apimPublisherName
    skuName: apimSku
    // Reference architecture: APIM -> backend orchestrator -> Foundry + Search.
    // Route to the selected backend host (Function or Container App) when
    // deployed; otherwise fall back to the raw Foundry endpoint (chat contract
    // will not match — a backend is expected for the widget contract).
    backendUrl: empty(backendFqdn) ? foundry.outputs.accountEndpoint : 'https://${backendFqdn}'
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    logAnalyticsId: monitoring.outputs.logAnalyticsId
    tags: tags
  }
}

module backend 'modules/containerapp.bicep' = if (deployContainerApp) {
  name: 'backend'
  params: {
    location: location
    environmentName: '${baseName}-cae'
    appName: '${baseName}-api'
    userAssignedIdentityId: identity.outputs.id
    userAssignedClientId: identity.outputs.clientId
    containerImage: backendImage
    foundryProjectEndpoint: foundry.outputs.projectEndpoint
    modelDeploymentName: foundry.outputs.modelDeploymentName
    searchEndpoint: search.outputs.endpoint
    searchIndex: searchIndexName
    searchSemanticConfig: 'county-semantic'
    embeddingDeploymentName: foundry.outputs.embeddingDeploymentName
    vectorEnabled: true
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    tags: tags
  }
}

module functionBackend 'modules/functionapp.bicep' = if (deployFunction) {
  name: 'functionBackend'
  params: {
    location: location
    planName: '${baseName}-fcplan'
    appName: '${baseName}-func-${shortSuffix}'
    storageAccountName: take('st${replace(suffix, '-', '')}', 24)
    userAssignedIdentityId: identity.outputs.id
    userAssignedClientId: identity.outputs.clientId
    principalId: identity.outputs.principalId
    foundryProjectEndpoint: foundry.outputs.projectEndpoint
    modelDeploymentName: foundry.outputs.modelDeploymentName
    searchEndpoint: search.outputs.endpoint
    searchIndex: searchIndexName
    searchSemanticConfig: 'county-semantic'
    embeddingDeploymentName: foundry.outputs.embeddingDeploymentName
    vectorEnabled: true
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    tags: tags
  }
}

// Resolve the backend URL APIM routes to, based on the selected host.
var backendFqdn = deployFunction
  ? functionBackend!.outputs.fqdn
  : (deployContainerApp ? backend!.outputs.fqdn : '')

// ----------------------------------------------------------------------------
// Outputs (feed these into .env / Named Values)
// ----------------------------------------------------------------------------
output managedIdentityClientId string = identity.outputs.clientId
output keyVaultUri string = keyvault.outputs.uri
output searchEndpoint string = search.outputs.endpoint
output searchIndexName string = searchIndexName
output foundryAccountEndpoint string = foundry.outputs.accountEndpoint
output foundryProjectEndpoint string = foundry.outputs.projectEndpoint
output modelDeploymentName string = foundry.outputs.modelDeploymentName
output embeddingDeploymentName string = foundry.outputs.embeddingDeploymentName
output apimGatewayUrl string = apim.outputs.gatewayUrl
output appInsightsConnectionString string = monitoring.outputs.appInsightsConnectionString
output backendHost string = backendHost
output backendFqdn string = backendFqdn

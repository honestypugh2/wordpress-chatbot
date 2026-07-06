// =============================================================================
// FinOps lookup tables + ingestion plumbing for per-user cost attribution.
//
// Provisions the custom Log Analytics tables the per-user FinOps dashboard/Workbook
// queries join against, plus the Data Collection Endpoint (DCE) + Data Collection
// Rule (DCR) needed to seed them via the Logs Ingestion API:
//
//   PRICING_CL          (Model, InputTokensPrice, OutputTokensPrice)   ← pricing
//   USER_QUOTA_CL       (UserId, CostQuota)                            ← budgets
//   USER_DIRECTORY_CL   (UserId, DisplayName, Upn)                     ← oid → name
//
// Schema is provisioned here; rows are seeded by scripts/seed_finops_tables.py
// (uses LogsIngestionClient against the DCE/DCR outputs below). The seeding
// identity needs "Monitoring Metrics Publisher" on the DCR — granted here to the
// workload managed identity and, optionally, to a developer/CI principal.
// =============================================================================

@description('Azure region.')
param location string

@description('Existing Log Analytics workspace name (created by the monitoring module).')
param logAnalyticsName string

@description('Base name used to derive resource names.')
param baseName string

@description('Short unique suffix for globally-scoped names.')
param shortSuffix string

@description('Workload managed identity principal id (granted Metrics Publisher on the DCR).')
param principalId string

@description('Optional developer/CI principal id also granted Metrics Publisher on the DCR (for running the seed script locally). Leave empty to skip.')
param seedPrincipalId string = ''

@description('Principal type for seedPrincipalId.')
@allowed([
  'User'
  'ServicePrincipal'
])
param seedPrincipalType string = 'User'

@description('Resource tags.')
param tags object = {}

// Monitoring Metrics Publisher — required to push rows via the Logs Ingestion API.
var metricsPublisherRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '3913510d-42f4-4e42-8a64-420c390055eb'
)

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsName
}

// ── Custom tables ────────────────────────────────────────────────────────────
resource pricingTable 'Microsoft.OperationalInsights/workspaces/tables@2022-10-01' = {
  parent: workspace
  name: 'PRICING_CL'
  properties: {
    totalRetentionInDays: 30
    schema: {
      name: 'PRICING_CL'
      columns: [
        { name: 'TimeGenerated', type: 'datetime' }
        { name: 'Model', type: 'string' }
        { name: 'InputTokensPrice', type: 'real' }
        { name: 'OutputTokensPrice', type: 'real' }
      ]
    }
  }
}

resource userQuotaTable 'Microsoft.OperationalInsights/workspaces/tables@2022-10-01' = {
  parent: workspace
  name: 'USER_QUOTA_CL'
  properties: {
    totalRetentionInDays: 30
    schema: {
      name: 'USER_QUOTA_CL'
      columns: [
        { name: 'TimeGenerated', type: 'datetime' }
        { name: 'UserId', type: 'string' }
        { name: 'CostQuota', type: 'real' }
      ]
    }
  }
}

resource userDirectoryTable 'Microsoft.OperationalInsights/workspaces/tables@2022-10-01' = {
  parent: workspace
  name: 'USER_DIRECTORY_CL'
  properties: {
    totalRetentionInDays: 30
    schema: {
      name: 'USER_DIRECTORY_CL'
      columns: [
        { name: 'TimeGenerated', type: 'datetime' }
        { name: 'UserId', type: 'string' }
        { name: 'DisplayName', type: 'string' }
        { name: 'Upn', type: 'string' }
      ]
    }
  }
}

// ── Ingestion endpoint + rule ────────────────────────────────────────────────
resource dce 'Microsoft.Insights/dataCollectionEndpoints@2023-03-11' = {
  name: '${baseName}-finops-dce-${shortSuffix}'
  location: location
  tags: tags
  properties: {
    networkAcls: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

resource dcr 'Microsoft.Insights/dataCollectionRules@2023-03-11' = {
  name: '${baseName}-finops-dcr-${shortSuffix}'
  location: location
  tags: tags
  properties: {
    dataCollectionEndpointId: dce.id
    streamDeclarations: {
      'Custom-PRICING_CL': {
        columns: [
          { name: 'TimeGenerated', type: 'datetime' }
          { name: 'Model', type: 'string' }
          { name: 'InputTokensPrice', type: 'real' }
          { name: 'OutputTokensPrice', type: 'real' }
        ]
      }
      'Custom-USER_QUOTA_CL': {
        columns: [
          { name: 'TimeGenerated', type: 'datetime' }
          { name: 'UserId', type: 'string' }
          { name: 'CostQuota', type: 'real' }
        ]
      }
      'Custom-USER_DIRECTORY_CL': {
        columns: [
          { name: 'TimeGenerated', type: 'datetime' }
          { name: 'UserId', type: 'string' }
          { name: 'DisplayName', type: 'string' }
          { name: 'Upn', type: 'string' }
        ]
      }
    }
    destinations: {
      logAnalytics: [
        {
          workspaceResourceId: workspace.id
          name: 'la-dest'
        }
      ]
    }
    dataFlows: [
      {
        streams: [ 'Custom-PRICING_CL' ]
        destinations: [ 'la-dest' ]
        transformKql: 'source'
        outputStream: 'Custom-PRICING_CL'
      }
      {
        streams: [ 'Custom-USER_QUOTA_CL' ]
        destinations: [ 'la-dest' ]
        transformKql: 'source'
        outputStream: 'Custom-USER_QUOTA_CL'
      }
      {
        streams: [ 'Custom-USER_DIRECTORY_CL' ]
        destinations: [ 'la-dest' ]
        transformKql: 'source'
        outputStream: 'Custom-USER_DIRECTORY_CL'
      }
    ]
  }
  dependsOn: [
    pricingTable
    userQuotaTable
    userDirectoryTable
  ]
}

// ── Ingestion permissions ────────────────────────────────────────────────────
resource miPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(dcr.id, principalId, 'metrics-publisher')
  scope: dcr
  properties: {
    roleDefinitionId: metricsPublisherRoleId
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource seedPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(seedPrincipalId)) {
  name: guid(dcr.id, seedPrincipalId, 'metrics-publisher')
  scope: dcr
  properties: {
    roleDefinitionId: metricsPublisherRoleId
    principalId: seedPrincipalId
    principalType: seedPrincipalType
  }
}

// ── Outputs (feed scripts/seed_finops_tables.py) ─────────────────────────────
output dceLogsIngestionEndpoint string = dce.properties.logsIngestion.endpoint
output dcrImmutableId string = dcr.properties.immutableId
output pricingStreamName string = 'Custom-PRICING_CL'
output userQuotaStreamName string = 'Custom-USER_QUOTA_CL'
output userDirectoryStreamName string = 'Custom-USER_DIRECTORY_CL'

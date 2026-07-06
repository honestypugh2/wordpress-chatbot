// ════════════════════════════════════════════════════════════════════════════
//  Per-User FinOps Dashboard tiles — APIM ❤️ AI Foundry
//
//  A drop-in companion to the upstream AI-Gateway FinOps dashboard
//  (Azure-Samples/AI-Gateway/labs/finops-framework/dashboard.bicep). The upstream
//  tiles attribute cost by `ApimSubscriptionId` (per APIM subscription / team).
//  These tiles attribute cost by the `UserId` dimension emitted by the `genai`
//  azure-openai-emit-token-metric in this repo's APIM policies — i.e. PER USER.
//
//  UserId precedence in the policy: Entra 'oid' (JWT, production) > x-user-id
//  (trusted proxy, demo/dev) > subscription id. So these tiles are wired to the
//  Entra JWT path automatically.
//
//  The tile queries run against the Log Analytics workspace (AppMetrics schema)
//  and price tokens via PRICING_CL exactly like the upstream dashboard:
//      cost = (PromptTokens*InputTokensPrice + CompletionTokens*OutputTokensPrice)/1000
//
//  Deploy standalone, OR copy the three `parts[]` entries into the upstream
//  dashboard.bicep `lenses[0].parts` array to merge them into that dashboard.
//
//  Prereqs:
//    • App Insights diagnostic on the AOAI API with metrics:true (so the genai
//      metric is published — see repo memory / README).
//    • PRICING_CL seeded with a row per resolved ModelName (the model-router
//      x-ms-served-model value, e.g. "gpt-4.1-2025-04-14"; or family names if you
//      normalize snapshot suffixes in the query).
//    • USER_QUOTA_CL seeded (UserId, CostQuota) for the budget tile.
// ════════════════════════════════════════════════════════════════════════════

@description('Suffix used to make the dashboard name unique within the resource group.')
param resourceSuffix string

@description('Log Analytics workspace name (shown as the tile subtitle).')
param workspaceName string

@description('Full resource id of the Log Analytics workspace the tiles query.')
param workspaceId string

// ── Per-user cost (current month) — donut ───────────────────────────────────
var perUserCostQuery = '''let pricing = PRICING_CL
| summarize arg_max(TimeGenerated, *) by Model
| project Model, InputTokensPrice, OutputTokensPrice;
AppMetrics
| where TimeGenerated >= startofmonth(now()) and TimeGenerated <= endofmonth(now())
| where Name in ("Prompt Tokens", "Completion Tokens")
| extend UserId = tostring(Properties["UserId"]), ModelName = tostring(Properties["ModelName"])
| where isnotempty(UserId) and UserId != "anonymous"
| summarize PromptTokens = sumif(Sum, Name == "Prompt Tokens"), CompletionTokens = sumif(Sum, Name == "Completion Tokens") by UserId, ModelName
| join kind=inner pricing on $left.ModelName == $right.Model
| extend InputCost = PromptTokens * InputTokensPrice, OutputCost = CompletionTokens * OutputTokensPrice
| summarize InputCost = sum(InputCost), OutputCost = sum(OutputCost) by UserId
| extend TotalCost = (InputCost + OutputCost) / 1000
| project UserId, TotalCost
| order by TotalCost desc
'''

// ── Per-user cost over time — column, split by user ─────────────────────────
var perUserOverTimeQuery = '''let pricing = PRICING_CL
| summarize arg_max(TimeGenerated, *) by Model
| project Model, InputTokensPrice, OutputTokensPrice;
AppMetrics
| where Name in ("Prompt Tokens", "Completion Tokens")
| extend UserId = tostring(Properties["UserId"]), ModelName = tostring(Properties["ModelName"])
| where isnotempty(UserId) and UserId != "anonymous"
| summarize PromptTokens = sumif(Sum, Name == "Prompt Tokens"), CompletionTokens = sumif(Sum, Name == "Completion Tokens") by UserId, ModelName, bin(TimeGenerated, 1h)
| join kind=inner pricing on $left.ModelName == $right.Model
| extend TotalCost = (PromptTokens * InputTokensPrice + CompletionTokens * OutputTokensPrice) / 1000
| summarize TotalCost = sum(TotalCost) by TimeGenerated, UserId
| project TimeGenerated, UserId, TotalCost
'''

// ── Per-user budget vs actual — column ──────────────────────────────────────
var perUserBudgetQuery = '''let pricing = PRICING_CL
| summarize arg_max(TimeGenerated, *) by Model
| project Model, InputTokensPrice, OutputTokensPrice;
let spend = AppMetrics
| where TimeGenerated >= startofmonth(now()) and TimeGenerated <= endofmonth(now())
| where Name in ("Prompt Tokens", "Completion Tokens")
| extend UserId = tostring(Properties["UserId"]), ModelName = tostring(Properties["ModelName"])
| where isnotempty(UserId) and UserId != "anonymous"
| summarize PromptTokens = sumif(Sum, Name == "Prompt Tokens"), CompletionTokens = sumif(Sum, Name == "Completion Tokens") by UserId, ModelName
| join kind=inner pricing on $left.ModelName == $right.Model
| extend InputCost = PromptTokens * InputTokensPrice, OutputCost = CompletionTokens * OutputTokensPrice
| summarize InputCost = sum(InputCost), OutputCost = sum(OutputCost) by UserId
| extend TotalCost = (InputCost + OutputCost) / 1000;
spend
| join kind=inner (USER_QUOTA_CL | summarize arg_max(TimeGenerated, *) by UserId | project UserId, CostQuota) on UserId
| project UserId, CostQuota, TotalCost
'''

resource perUserFinOpsDashboard 'Microsoft.Portal/dashboards@2022-12-01-preview' = {
  name: guid(resourceGroup().id, resourceSuffix, 'perUserFinOpsDashboard')
  location: resourceGroup().location
  tags: {
    'hidden-title': 'APIM ❤️ AI Foundry — Per-User FinOps'
  }
  properties: {
    lenses: any([
      {
        order: 0
        parts: [
          // Tile 1 — AI cost by user (MTD), donut
          {
            position: { x: 0, y: 0, rowSpan: 4, colSpan: 7 }
            metadata: {
              inputs: [
                { name: 'resourceTypeMode', isOptional: true }
                { name: 'ComponentId', isOptional: true }
                { name: 'Scope', value: { resourceIds: [ workspaceId ] }, isOptional: true }
                { name: 'PartId', value: 'a1111111-1111-4111-8111-111111111111', isOptional: true }
                { name: 'Version', value: '2.0', isOptional: true }
                { name: 'TimeRange', value: 'P30D', isOptional: true }
                { name: 'DashboardId', isOptional: true }
                { name: 'DraftRequestParameters', isOptional: true }
                { name: 'Query', value: perUserCostQuery, isOptional: true }
                { name: 'ControlType', value: 'FrameControlChart', isOptional: true }
                { name: 'SpecificChart', value: 'Donut', isOptional: true }
                { name: 'PartTitle', value: 'AI cost by user (MTD)', isOptional: true }
                { name: 'PartSubTitle', value: workspaceName, isOptional: true }
                {
                  name: 'Dimensions'
                  value: {
                    xAxis: { name: 'UserId', type: 'string' }
                    yAxis: [ { name: 'TotalCost', type: 'real' } ]
                    splitBy: []
                    aggregation: 'Sum'
                  }
                  isOptional: true
                }
                { name: 'LegendOptions', value: { isEnabled: true, position: 'Bottom' }, isOptional: true }
                { name: 'IsQueryContainTimeRange', value: true, isOptional: true }
              ]
              type: 'Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart'
              settings: {}
            }
          }
          // Tile 2 — AI spend over time by user, column
          {
            position: { x: 7, y: 0, rowSpan: 4, colSpan: 8 }
            metadata: {
              inputs: [
                { name: 'resourceTypeMode', isOptional: true }
                { name: 'ComponentId', isOptional: true }
                { name: 'Scope', value: { resourceIds: [ workspaceId ] }, isOptional: true }
                { name: 'PartId', value: 'a2222222-2222-4222-8222-222222222222', isOptional: true }
                { name: 'Version', value: '2.0', isOptional: true }
                { name: 'TimeRange', value: 'P30D', isOptional: true }
                { name: 'DashboardId', isOptional: true }
                { name: 'DraftRequestParameters', isOptional: true }
                { name: 'Query', value: perUserOverTimeQuery, isOptional: true }
                { name: 'ControlType', value: 'FrameControlChart', isOptional: true }
                { name: 'SpecificChart', value: 'StackedColumn', isOptional: true }
                { name: 'PartTitle', value: 'AI spend over time by user', isOptional: true }
                { name: 'PartSubTitle', value: workspaceName, isOptional: true }
                {
                  name: 'Dimensions'
                  value: {
                    xAxis: { name: 'TimeGenerated', type: 'datetime' }
                    yAxis: [ { name: 'TotalCost', type: 'real' } ]
                    splitBy: [ { name: 'UserId', type: 'string' } ]
                    aggregation: 'Sum'
                  }
                  isOptional: true
                }
                { name: 'LegendOptions', value: { isEnabled: true, position: 'Bottom' }, isOptional: true }
                { name: 'IsQueryContainTimeRange', value: false, isOptional: true }
              ]
              type: 'Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart'
              settings: {}
            }
          }
          // Tile 3 — Budget vs actual by user, column
          {
            position: { x: 0, y: 4, rowSpan: 4, colSpan: 7 }
            metadata: {
              inputs: [
                { name: 'resourceTypeMode', isOptional: true }
                { name: 'ComponentId', isOptional: true }
                { name: 'Scope', value: { resourceIds: [ workspaceId ] }, isOptional: true }
                { name: 'PartId', value: 'a3333333-3333-4333-8333-333333333333', isOptional: true }
                { name: 'Version', value: '2.0', isOptional: true }
                { name: 'TimeRange', value: 'P30D', isOptional: true }
                { name: 'DashboardId', isOptional: true }
                { name: 'DraftRequestParameters', isOptional: true }
                { name: 'Query', value: perUserBudgetQuery, isOptional: true }
                { name: 'ControlType', value: 'FrameControlChart', isOptional: true }
                { name: 'SpecificChart', value: 'UnstackedColumn', isOptional: true }
                { name: 'PartTitle', value: 'Budget vs actual by user', isOptional: true }
                { name: 'PartSubTitle', value: workspaceName, isOptional: true }
                {
                  name: 'Dimensions'
                  value: {
                    xAxis: { name: 'UserId', type: 'string' }
                    yAxis: [ { name: 'CostQuota', type: 'real' }, { name: 'TotalCost', type: 'real' } ]
                    splitBy: []
                    aggregation: 'Sum'
                  }
                  isOptional: true
                }
                { name: 'LegendOptions', value: { isEnabled: true, position: 'Bottom' }, isOptional: true }
                { name: 'IsQueryContainTimeRange', value: true, isOptional: true }
              ]
              type: 'Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart'
              settings: {}
            }
          }
        ]
      }
    ])
    metadata: {
      model: {
        timeRange: {
          value: { relative: { duration: 24, timeUnit: 1 } }
          type: 'MsPortalFx.Composition.Configuration.ValueTypes.TimeRange'
        }
        filterLocale: { value: 'en-us' }
      }
    }
  }
}

@description('Resource id of the per-user FinOps dashboard.')
output dashboardId string = perUserFinOpsDashboard.id

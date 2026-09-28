-- Civ VI UI context: export only plots currently visible to the local player.
-- The companion server reads Lua.log. This mod never sends network requests.
local MARKER = "CIV6AI_V2|"
local counter = 0

local function call(object, method, ...)
  if object == nil then return nil end
  local ok, result = pcall(function(...) return object[method](object, ...) end, ...)
  if ok then return result end
  return nil
end

local function typename(info, index, field)
  if not index or index == -1 then return nil end
  local row = info[index]
  return row and row[field] or nil
end

local function quoted(value)
  local stringValue = tostring(value):gsub('\\', '\\\\'):gsub('"', '\\"')
  stringValue = stringValue:gsub('[%z\1-\31]', function(character)
    return string.format('\\u%04x', string.byte(character))
  end)
  return '"' .. stringValue .. '"'
end

local function encode(item)
  local parts = {}
  for key, value in pairs(item) do
    if value ~= nil then
      local encoded = nil
      if type(value) == 'number' or type(value) == 'boolean' then encoded = tostring(value) end
      parts[#parts + 1] = quoted(key) .. ':' .. (encoded or quoted(value))
    end
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

local function traitDescriptions(tableName, column, typeValue)
  if not typeValue then return nil end
  local descriptions = {}
  for row in GameInfo[tableName]() do
    if row[column] == typeValue then
      local trait = GameInfo.Traits[row.TraitType]
      local description = trait and trait.Description and Locale.Lookup(trait.Description) or ''
      descriptions[#descriptions + 1] = row.TraitType .. ': ' .. description
    end
  end
  return table.concat(descriptions, '; ')
end

local function districts(city)
  local existing = {}
  for row in GameInfo.Districts() do
    if call(city:GetDistricts(), 'HasDistrict', row.Index) then
      existing[#existing + 1] = row.DistrictType
    end
  end
  return table.concat(existing, ',')
end

local function snapshot()
  local playerID = Game.GetLocalPlayer()
  if playerID == nil or playerID < 0 then return nil end
  local player = Players[playerID]
  if not player then return nil end
  local setup = PlayerConfigurations[playerID]
  local civ = setup and setup:GetCivilizationTypeName() or nil
  local leader = setup and setup:GetLeaderTypeName() or nil
  local results = {{
    kind='meta', turn=Game.GetCurrentGameTurn(), player_id=playerID,
    civilization=civ, leader=leader,
    civilization_traits=traitDescriptions('CivilizationTraits', 'CivilizationType', civ),
    leader_traits=traitDescriptions('LeaderTraits', 'LeaderType', leader),
    current_tech=typename(GameInfo.Technologies, call(call(player,'GetTechs'),'GetResearchingTech'), 'TechnologyType'),
    current_civic=typename(GameInfo.Civics, call(call(player,'GetCulture'),'GetProgressingCivic'), 'CivicType'),
    gold=call(call(player,'GetTreasury'),'GetGoldBalance')
  }}
  local candidates = {}
  local function includeNearby(x,y)
    for _, plot in ipairs(Map.GetNeighborPlots(x,y,3) or {}) do
      candidates[plot:GetIndex()] = plot
    end
  end
  for _, city in player:GetCities():Members() do
    local x,y = city:GetX(), city:GetY()
    local growth = call(city,'GetGrowth')
    local queue = call(city,'GetBuildQueue')
    results[#results+1] = {kind='city',id=city:GetID(),name=Locale.Lookup(city:GetName()),
      x=x,y=y,population=city:GetPopulation(),housing=call(growth,'GetHousing'),
      amenities=call(growth,'GetAmenities'),production_hash=call(queue,'CurrentlyBuilding'),
      districts=districts(city)}
    includeNearby(x,y)
  end
  local settler = GameInfo.Units['UNIT_SETTLER']
  for _, unit in player:GetUnits():Members() do
    local x,y = unit:GetX(),unit:GetY()
    results[#results+1] = {kind='unit',id=unit:GetID(),type=typename(GameInfo.Units,unit:GetType(),'UnitType'),
      x=x,y=y,moves=call(unit,'GetMovesRemaining')}
    if settler and unit:GetType() == settler.Index then includeNearby(x,y) end
  end
  local visibility = PlayerVisibilityManager.GetPlayerVisibility(playerID)
  for _, plot in pairs(candidates) do
    local x,y=plot:GetX(),plot:GetY()
    if visibility and visibility:IsVisible(x,y) then
      results[#results+1]={kind='plot',x=x,y=y,owner=plot:GetOwner(),
        terrain=typename(GameInfo.Terrains,plot:GetTerrainType(),'TerrainType'),
        feature=typename(GameInfo.Features,plot:GetFeatureType(),'FeatureType'),
        resource=typename(GameInfo.Resources,plot:GetResourceType(),'ResourceType'),
        district=typename(GameInfo.Districts,plot:GetDistrictType(),'DistrictType'),
        improvement=typename(GameInfo.Improvements,plot:GetImprovementType(),'ImprovementType'),
        food=plot:GetYield(YieldTypes.FOOD),production=plot:GetYield(YieldTypes.PRODUCTION),
        science=plot:GetYield(YieldTypes.SCIENCE),culture=plot:GetYield(YieldTypes.CULTURE),
        gold=plot:GetYield(YieldTypes.GOLD),faith=plot:GetYield(YieldTypes.FAITH),
        river=plot:IsRiver(),hills=plot:IsHills(),water=plot:IsWater()}
    end
  end
  return results
end

local function export()
  local ok, items = pcall(snapshot)
  if not ok or not items then
    print('CIV6AI_ERROR: ' .. tostring(items))
    Controls.ExportLabel:SetText('匯出失敗')
    return
  end
  counter=counter+1
  local token=tostring(Game.GetCurrentGameTurn()*10000+counter)
  print(MARKER..token..'|BEGIN|'..#items..'|{}')
  for index,item in ipairs(items) do print(MARKER..token..'|ITEM|'..index..'|'..encode(item)) end
  print(MARKER..token..'|END|'..#items..'|{}')
  Controls.ExportLabel:SetText('已匯出 '..#items..' 筆')
end

Controls.ExportButton:RegisterCallback(Mouse.eLClick,export)
print('CIV6AI: UI loaded')

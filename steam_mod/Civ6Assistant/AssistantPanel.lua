-- UI context only: read local player's visible state; never issue game commands.
local exportCounter = 0
local PREFIX = "CIV6_ASSISTANT_V1|"

local function safe(object, method, ...)
  if object == nil then return nil end
  local ok, value = pcall(function(...) return object[method](object, ...) end, ...)
  if ok then return value end
  return nil
end

local function typeName(info, index, field)
  if index == nil or index == -1 then return nil end
  local row = info[index]
  if row then return row[field] end
  return nil
end

local function quote(value)
  local s = tostring(value):gsub('\\', '\\\\'):gsub('"', '\\"')
  s = s:gsub('[%z\1-\31]', function(char)
    if char == '\n' then return '\\n' end
    if char == '\r' then return '\\r' end
    return string.format('\\u%04x', string.byte(char))
  end)
  return '"' .. s .. '"'
end

local function json(record)
  local fields = {}
  for key, value in pairs(record) do
    if value ~= nil then
      local rendered
      if type(value) == "number" then rendered = tostring(value)
      elseif type(value) == "boolean" then rendered = tostring(value)
      else rendered = quote(value) end
      fields[#fields + 1] = quote(key) .. ':' .. rendered
    end
  end
  return '{' .. table.concat(fields, ',') .. '}'
end

local function traits(tableName, key, value)
  local values = {}
  for row in GameInfo[tableName]() do
    if row[key] == value then
      local trait = GameInfo.Traits[row.TraitType]
      local description = trait and trait.Description and Locale.Lookup(trait.Description) or ""
      values[#values + 1] = row.TraitType .. ": " .. description
    end
  end
  return table.concat(values, ',')
end

local function collect()
  local id = Game.GetLocalPlayer()
  if id == nil or id < 0 then return nil end
  local player = Players[id]
  if not player then return nil end
  local config = PlayerConfigurations[id]
  local civ = config and config:GetCivilizationTypeName() or nil
  local leader = config and config:GetLeaderTypeName() or nil
  local result = {{
    kind = "meta", turn = Game.GetCurrentGameTurn(), player_id = id,
    civilization = civ, leader = leader,
    civ_traits = civ and traits("CivilizationTraits", "CivilizationType", civ) or nil,
    leader_traits = leader and traits("LeaderTraits", "LeaderType", leader) or nil,
    current_tech = typeName(GameInfo.Technologies, safe(safe(player, "GetTechs"), "GetResearchingTech"), "TechnologyType"),
    current_civic = typeName(GameInfo.Civics, safe(safe(player, "GetCulture"), "GetProgressingCivic"), "CivicType"),
    gold = safe(safe(player, "GetTreasury"), "GetGoldBalance"),
    science_per_turn = safe(safe(player, "GetTechs"), "GetScienceYield"),
    culture_per_turn = safe(safe(player, "GetCulture"), "GetCultureYield"),
  }}
  local candidates = {}
  for _, city in player:GetCities():Members() do
    local x, y = city:GetX(), city:GetY()
    local growth = safe(city, "GetGrowth")
    local queue = safe(city, "GetBuildQueue")
    result[#result + 1] = {
      kind = "city", id = city:GetID(), name = Locale.Lookup(city:GetName()), x = x, y = y,
      population = city:GetPopulation(), housing = safe(growth, "GetHousing"),
      amenities = safe(growth, "GetAmenities"), food_surplus = safe(growth, "GetFoodSurplus"),
      production = safe(queue, "CurrentlyBuilding"),
    }
    for _, plot in ipairs(Map.GetNeighborPlots(x, y, 3) or {}) do
      candidates[plot:GetIndex()] = plot
    end
  end
  for _, unit in player:GetUnits():Members() do
    local x, y = unit:GetX(), unit:GetY()
    result[#result + 1] = {
      kind = "unit", id = unit:GetID(), type = typeName(GameInfo.Units, unit:GetType(), "UnitType"),
      x = x, y = y, moves = safe(unit, "GetMovesRemaining"),
    }
    if safe(unit, "GetType") == (GameInfo.Units["UNIT_SETTLER"] or {}).Index then
      for _, plot in ipairs(Map.GetNeighborPlots(x, y, 3) or {}) do
        candidates[plot:GetIndex()] = plot
      end
    end
  end
  local visibility = PlayerVisibilityManager.GetPlayerVisibility(id)
  for _, plot in pairs(candidates) do
    local x, y = plot:GetX(), plot:GetY()
    if visibility and visibility:IsVisible(x, y) then
      result[#result + 1] = {
        kind = "plot", x = x, y = y, owner = plot:GetOwner(),
        terrain = typeName(GameInfo.Terrains, plot:GetTerrainType(), "TerrainType"),
        feature = typeName(GameInfo.Features, plot:GetFeatureType(), "FeatureType"),
        resource = typeName(GameInfo.Resources, plot:GetResourceType(), "ResourceType"),
        district = typeName(GameInfo.Districts, plot:GetDistrictType(), "DistrictType"),
        improvement = typeName(GameInfo.Improvements, plot:GetImprovementType(), "ImprovementType"),
        food = plot:GetYield(YieldTypes.FOOD), production = plot:GetYield(YieldTypes.PRODUCTION),
        science = plot:GetYield(YieldTypes.SCIENCE), culture = plot:GetYield(YieldTypes.CULTURE),
        gold = plot:GetYield(YieldTypes.GOLD), faith = plot:GetYield(YieldTypes.FAITH),
        river = plot:IsRiver(), hills = plot:IsHills(), water = plot:IsWater(),
      }
    end
  end
  return result
end

local function export()
  local ok, records = pcall(collect)
  if not ok or not records then
    print("CIV6_ASSISTANT_ERROR: " .. tostring(records))
    return
  end
  exportCounter = exportCounter + 1
  local session = tostring(Game.GetCurrentGameTurn() * 10000 + exportCounter)
  print(PREFIX .. session .. "|BEGIN|" .. #records .. "|{}")
  for index, item in ipairs(records) do
    print(PREFIX .. session .. "|ITEM|" .. index .. "|" .. json(item))
  end
  print(PREFIX .. session .. "|END|" .. #records .. "|{}")
  print("CIV6_ASSISTANT: exported " .. #records .. " records")
end

Controls.ExportButton:RegisterCallback(Mouse.eLClick, export)
print("CIV6_ASSISTANT: UI loaded")

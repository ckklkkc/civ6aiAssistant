-- Civ VI UI context: export only plots currently visible to the local player.
-- The Windows companion reads Lua.log and pastes response frames into ReplyInput.
local MARKER = "CIV6AI_V2|"
local CHAT = "CIV6AI_CHAT_V1|"
local counter = 0
local activeToken = nil
local pages = {}
local currentPage = 1
local receiving = false

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
    Controls.Status:SetText('遊戲資料取得失敗；請查看 Lua.log 的 CIV6AI_ERROR。')
    return nil
  end
  counter=counter+1
  local token=tostring(Game.GetCurrentGameTurn()*10000+counter)
  print(MARKER..token..'|BEGIN|'..#items..'|{}')
  for index,item in ipairs(items) do print(MARKER..token..'|ITEM|'..index..'|'..encode(item)) end
  print(MARKER..token..'|END|'..#items..'|{}')
  return token
end

local function showPage()
  if #pages == 0 then
    Controls.Page:SetText('0 / 0')
    return
  end
  currentPage = math.max(1,math.min(currentPage,#pages))
  -- Never interpret model text as Civ VI [COLOR] or [ICON] markup.
  local plain = pages[currentPage]:gsub('%[','('):gsub('%]',')')
  Controls.Answer:SetText(plain)
  Controls.Page:SetText(currentPage..' / '..#pages)
end

local function ask()
  local question = Controls.QuestionBox:GetText()
  if not question or question == '' then
    Controls.Status:SetText('請先輸入問題。')
    return
  end
  local token=export()
  if not token then return end
  activeToken=token
  pages={}
  currentPage=1
  Controls.Answer:SetText('正在分析局勢…')
  Controls.Page:SetText('0 / 0')
  Controls.Status:SetText('問題已送出。稍後按「接收回答」。')
  print(CHAT..token..'|ASK|'..encode({question=question}))
end

local function receive()
  if not activeToken then
    Controls.Status:SetText('請先按「詢問 AI」。')
    return
  end
  Controls.ReplyInput:SetText('')
  Controls.ReplyInput:TakeFocus()
  Controls.Status:SetText('等待接收…若尚未完成，幾秒後再按此按鈕。')
  print(CHAT..activeToken..'|READY|{}')
end

local function onReplyChanged()
  if receiving or not activeToken then return end
  local value=Controls.ReplyInput:GetText()
  if not value then return end
  local token,sequence,total,part=value:match('^CIV6AI_REPLY|(%d+)|(%d+)|(%d+)|(.+)$')
  sequence=tonumber(sequence)
  total=tonumber(total)
  if token ~= activeToken or not sequence or not total or total > 40 or sequence < 1 or sequence > total then return end
  if sequence == 1 then pages={} end
  if sequence ~= #pages+1 then return end
  receiving=true
  pages[#pages+1]=part
  currentPage=#pages
  showPage()
  Controls.ReplyInput:SetText('')
  Controls.ReplyInput:TakeFocus()
  receiving=false
  print(CHAT..activeToken..'|ACK|'..sequence)
  if sequence == total then
    currentPage=1
    showPage()
    Controls.Status:SetText('回答已接收。可用「上頁／下頁」閱讀。')
  else
    Controls.Status:SetText('接收回答 '..sequence..' / '..total)
  end
end

Controls.OpenButton:RegisterCallback(Mouse.eLClick,function() Controls.Panel:SetHide(false) end)
Controls.CloseButton:RegisterCallback(Mouse.eLClick,function() Controls.Panel:SetHide(true) end)
Controls.AskButton:RegisterCallback(Mouse.eLClick,ask)
Controls.ReceiveButton:RegisterCallback(Mouse.eLClick,receive)
Controls.ReplyInput:RegisterStringChangedCallback(onReplyChanged)
Controls.Previous:RegisterCallback(Mouse.eLClick,function() currentPage=currentPage-1;showPage() end)
Controls.Next:RegisterCallback(Mouse.eLClick,function() currentPage=currentPage+1;showPage() end)
local samples={
  VictoryButton='根據我的文明與領袖特性，優先追求哪種勝利？',
  SettleButton='附近可見地塊適合在哪些座標建城？',
  BuildButton='我的城市下一項生產應該選什麼？',
  DistrictButton='區域如何布局？請標明候選座標與前置條件。',
  ResearchButton='接下來的科技與市政應如何排序？'
}
for id,question in pairs(samples) do
  Controls[id]:RegisterCallback(Mouse.eLClick,function() Controls.QuestionBox:SetText(question) end)
end
print('CIV6AI: in-game advisor UI loaded')

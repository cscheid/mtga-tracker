import json

from mtga.set_data import all_mtga_cards, all_mtga_abilities

##############################################################################
# This is an ugly, currently-necessary hack because
# describing abilities requires resolving instance ids to objects,
# which means we need to know about the currently-active log reader.
# this will have ugly consequences, I'm sure.

import log_reader

current_game = None
def register_current_game(game):
    global current_game
    current_game = game

##############################################################################
# python-mtga interop

def ability_name(obj):
    return all_mtga_abilities[obj.grpId]

def card_name(obj):
    oid = obj.grpId
    try:
        return all_mtga_cards.find_one(oid).pretty_name
    except ValueError:
        return "<Unknown card %s>" % oid

##############################################################################

def toupper(w):
    initial = w[0].upper()
    return initial + w[1:]

def tolower(w):
    initial = w[0].lower()
    return initial + w[1:]

def enum_name(tagged_name):
    return tolower(tagged_name.split("_")[1])

def enum_tuple(tagged_name):
    ttype, tname = tagged_name.split("_")
    return ttype, tolower(tname)

##############################################################################

class Obj:
    def __str__(self):
        return json.dumps(obj_to_json(self), indent=2)
    def copy(self):
        # quite inefficient, :shrug:
        return json_to_obj(obj_to_json(self))

##############################################################################
# we use verb_noun() notation for two (really one) reasons: it helps
# distinguish methods more clearly from the fields, and mtga log
# fields don't have underscores, so this also prevents us from clashing
# methods and fields directly.

# note that this is not _entirely_ safe, since tagged key-value pairs
# *do* have "key" fields with underscores, and we convert them into
# fields with underscores in the untagging magic below.

class MtgaLogObject(Obj):
    pass

##############################################################################
# GameObject

class GameObjectType(MtgaLogObject):
    def is_card(self):
        return False
    def get_zone(self):
        return current_game.resolve_object(self.zoneId)
    def get_controller(self):
        return current_game.resolve_object(self.controllerSeatId)

class GameObjectType_Ability(GameObjectType):
    def get_name(self):
        try:
            ability_text = all_mtga_abilities[self.grpId]
            if "~" in ability_text:
                parent_obj = current_game.resolve_object(self.parentId)
                parent_name = parent_obj.get_name()
                ability_text = ability_text.replace("~", parent_name)
            return ability_text
        except KeyError:
            return "<Unknown ability %s>" % self.grpId
    def describe(self):
        return "[%s] %s (%s)" % (self.instanceId, self.get_name(), self.parentId)

class GameObjectType_BaseCard(GameObjectType):
          
    def get_is_tapped(self):
        return getattr(self, "isTapped", False)
    
    def get_name(self):
        oid = self.grpId
        try:
            return all_mtga_cards.find_one(oid).pretty_name
        except ValueError:
            return "<Unknown card %s>" % oid

    def describe(self):
        cardname = self.get_name()
        return "[%s] %s%s" % (self.instanceId,
                              cardname,
                              " (tapped)" if self.get_is_tapped() else "")
    
class GameObjectType_Card(GameObjectType_BaseCard):
    def is_card(self):
        return True

class GameObjectType_RevealedCard(GameObjectType_BaseCard):
    def is_card(self):
        return True

class GameObjectType_SplitCard(GameObjectType_BaseCard):
    def is_card(self):
        return True

class GameObjectType_Token(GameObjectType_BaseCard):
    pass

##############################################################################
# Annotations

class AnnotationType(Obj):
    pass

class AnnotationType_ManaPaid(AnnotationType):
    def get_affector(self):
        return current_game.resolve_object(self.affectorId)
    def get_affected(self):
        result = list(current_game.resolve_object(i)
                      for i in self.affectedIds)
        if len(result) == 1:
            return result[0]
        else:
            return result

##############################################################################
# KeyValuePair

class KeyValuePair(Obj):
    def get_value(self):
        t = toupper(enum_name(self.type))
        result = getattr(self, 'value' + t)
        if len(result) == 1:
            return result[0]
        else:
            return result
        # assert(len(result) == 1)
        # return result[0]

class KeyValuePairValueType_int32(KeyValuePair):
    pass

class KeyValuePairValueType_string(KeyValuePair):
    pass

##############################################################################
# Zones

class Zone(Obj):
    def describe_source(self, expected):
        self_type = enum_name(self.type)
        if self_type == expected:
            return ""
        elif self_type == "exile":
            return " from exile"
        else:
            return " from their " + self_type
    def describe_destination(self, expected):
        self_type = enum_name(self.type)
        if self_type == expected:
            return ""
        elif self_type == "exile":
            return " and goes to exile"
        else:
            return " and goes to their " + self_type

class ZoneType_Battlefield(Zone):
    pass

class ZoneType_Hand(Zone):
    pass

class ZoneType_Graveyard(Zone):
    pass

class ZoneType_Library(Zone):
    pass

class ZoneType_Stack(Zone):
    pass

class ZoneType_Exile(Zone):
    pass

##############################################################################
# Player

class ControllerType_Player(Obj):
    def describe(self):
        return "P%s" % self.controllerSeatId

# very weird - one player became a goldfish mid-match!?
class ControllerType_AI_Goldfish(Obj):
    def describe(self):
        return "P%s" % self.controllerSeatId

##############################################################################
# fancy recursive imports to free-roll dynamic dispatch

import mtga_log_object
    
def construct_object(d):
    if "type" in d and type(d["type"]) == list and len(d["type"]) == 1:
        result = getattr(mtga_log_object, d["type"][0], Obj)()
    elif "type" in d and type(d["type"]) == str:
        result = getattr(mtga_log_object, d["type"], Obj)()
    elif "controllerType" in d and type(d["controllerType"]) == str:
        result = getattr(mtga_log_object, d["controllerType"], Obj)()
    else:
        result = Obj()
    for (k, v) in d.items():
        setattr(result, k, json_to_obj(v))
    return result

def is_key_value_pair(x):
    if isinstance(x, KeyValuePair):
        return True
    elif isinstance(x, Obj) and list(x.__dict__.keys()) == ["key"]:
        return True
    return False

def json_to_obj(json):
    def to_pair(tkv):
        try:
            return (tkv.key, tkv.get_value())
        except AttributeError:
            return (tkv.key, None)
    if type(json) == dict:
        return construct_object(json)
    elif type(json) == list:
        result = list(json_to_obj(l) for l in json)
        if len(result) > 0 and all(is_key_value_pair(x) for x in result):
            untagged_dict = dict(to_pair(tkv) for tkv in result)
            return json_to_obj(untagged_dict)
        else:
            return result
    else:
        return json

def obj_to_json(obj):
    if type(obj) == list:
        return list(obj_to_json(l) for l in obj)
    elif isinstance(obj, Obj):
        return dict((k, obj_to_json(v)) for (k,v) in obj.__dict__.items())
    else: # literal
        return obj

class LogEntry:
    def __init__(self, id, start, end):
        self.id = id
        self.start = start
        self.end = end
    def read_entry(self, f):
        f.seek(self.start)
        return json_to_obj(json.loads(f.read(self.end - self.start).decode("ascii")))
    def call_id(self):
        n = self.id
        return int(n[n.find("(")+1:n.find(")")])

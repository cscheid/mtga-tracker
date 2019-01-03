import os
import pickle
import hashlib
import json
import sys
import time
import crayons
import threading
import metagame_db
import logging

from mtga_log_object import *

logfile = os.getenv("APPDATA")+"\..\LocalLow\Wizards Of The Coast\MTGA\output_log.txt"
pickle_file = logfile[:-4] + ".pickle"

##############################################################################
# Mana Colors

colors = {
    1: "W",
    2: "U",
    3: "B",
    4: "R",
    5: "G"
    }
           
##############################################################################

CRITICAL=-10

class GameAnalysis:
    def __init__(self, events, log_level=5):
        
        self.events = events
        self.turn_info = Obj()
        self.id_change_map = {}
        self.total_mana_spent = {}
        self.unique_ids = {}
        self.unique_objects = {}
        self.log_level = log_level
        
        # self.analyze()
    
    ##########################################################################
    # For the meta DB

    def game_record(self):
        cards = self.cards_played()
        play = self.die_roll_winner
        draw = 3-self.die_roll_winner # 3-1 = 2, 3-2 = 1, "get the other seat"
        player_names = [self.seat_to_player_config[play].playerName,
                        self.seat_to_player_config[draw].playerName]
        return {
            "matchId": self.match_id,
            "gameId": self.game_id,
            "timestamp": self.timestamp,
            "playerNames": player_names,
            "cardsPlayed": cards,
            "winner": 0 if self.game_winner == self.die_roll_winner else 1,
            "superFormat": self.super_format
            }
    
    ##########################################################################
    # report
    
    def log_print(self, message, log_level=0):
        if log_level <= self.log_level:
            print(message)
    
    ##########################################################################
    # Analysis
    
    def cards_played(self):
        d = {}
        for obj in sorted(list(self.unique_objects.items()),
                          key=lambda kv: kv[1][2]):
            d.setdefault(obj[1][0], []).append(obj[1][1])
        d = sorted(list((k, v) for (k, v) in d.items()),
                   key=lambda kv: 0 if kv[0] == self.die_roll_winner else 1)
        for (k,v) in d:
            who = "us" if self.seat_to_player_config[k].playerName == self.our_name else "opp"
            self.log_print("Player %d (%s):" % (k, who))
            for name in v:
                self.log_print("  %s" % name)
        return [d[0][1], d[1][1]]
    
    ##########################################################################
    
    def handle_matchGameRoomStateChangedEvent(self, event):
        if event.gameRoomInfo.stateType == "MatchGameRoomStateType_Playing":
            self.seat_to_player_config = dict(
                (player.systemSeatId, player) for
                player in event.gameRoomInfo.gameRoomConfig.reservedPlayers)
            self.match_id     = event.gameRoomInfo.gameRoomConfig.matchId
            self.log_print("Analyzing game from match %s" % self.match_id)
            for player in self.seat_to_player_config.values():
                if player.userId == self.our_id:
                    self.log_print("  We:  %s, P%s" % (self.our_name, player.systemSeatId))
                else:
                    self.log_print("  Opp: %s, P%s" % (player.playerName, player.systemSeatId))
    
    ##########################################################################
    # game state management
    
    def resolve_object(self, object_id):
        if object_id in self.seat_to_player:
            return self.seat_to_player[object_id]
        if object_id in self.zones:
            return self.zones[object_id]
        while not object_id in self.instance_to_game_object:
            object_id = self.id_change_map[object_id]
        return self.instance_to_game_object[object_id]
    
    def try_resolve_object(self, object_id):
        try:
            return self.resolve_object(object_id)
        except KeyError:
            return None
    
    def battlefield_ids(self):
        return set(getattr(self.battlefield, "objectInstanceIds", []))
    
    def stack_ids(self):
        return getattr(self.stack, "objectInstanceIds", [])
    
    def stack_diff(self, stack_1, stack_2):
        stack_2 = set(stack_2)
        return list(i for i in stack_1 if i not in stack_2)
    
    def update_game_state_from_diff(self, msg):
        msg = msg.copy()
        prev_battlefield_ids = self.battlefield_ids()
        prev_stack_ids = self.stack_ids()
        prev_turn = getattr(self.turn_info, "turnNumber", 0)
        self.register_turn_info(getattr(msg, "turnInfo", Obj()))
        this_turn = getattr(self.turn_info, "turnNumber", 0)
        
        self.register_zones(getattr(msg, "zones", []))
        self.register_objects(getattr(msg, "gameObjects", []))
        self.register_players(getattr(msg, "players", []))
        self.handle_annotations(getattr(msg, "annotations", []))
        this_battlefield_ids = self.battlefield_ids()
        this_stack_ids = self.stack_ids()
        
        new_battlefield_objs = this_battlefield_ids.difference(prev_battlefield_ids)
        gone_battlefield_objs = prev_battlefield_ids.difference(this_battlefield_ids)
        
        new_stack_objs = self.stack_diff(this_stack_ids, prev_stack_ids)
        gone_stack_objs = self.stack_diff(prev_stack_ids, this_stack_ids)
        
        ######################################################################
        # report stuff
        
        if this_turn != prev_turn:
            self.log_print("\n  Turn started: %s" % this_turn)
            self.log_print("    P1: % 3d life, % 3d cards in hand" % (
                self.seat_to_player[1].lifeTotal,
                len(getattr(self.seat_to_hand[1], 'objectInstanceIds', []))))
            self.log_print("    P2: % 3d life, % 3d cards in hand" % (
                self.seat_to_player[2].lifeTotal,
                len(getattr(self.seat_to_hand[2], 'objectInstanceIds', []))))
        
        # if len(gone_stack_objs):
        #     for objId in gone_stack_objs:
        #         try:
        #             obj = self.instance_to_game_object[objId]
        #             self.log_print("    LTS: %s" % describe_obj(obj))
        #         except KeyError:
        #             self.log_print("    LTS: [Unknown object %s]" % objId)
        # if len(new_battlefield_objs):
        #     for objId in new_battlefield_objs:
        #         try:
        #             obj = self.instance_to_game_object[objId]
        #             self.log_print("    ETB: %s" % describe_card(obj))
        #         except KeyError:
        #             self.log_print("    ETB: [Unknown object %s]" % objId)
        
        # if len(gone_battlefield_objs):
        #     for objId in gone_battlefield_objs:
        #         try:
        #             obj = self.instance_to_game_object[objId]
        #             self.log_print("    LTB: %s" % describe_obj(obj))
        #         except KeyError:
        #             self.log_print("    LTB: [Unknown object %s]" % objId)
        
        if len(new_stack_objs):
            for objId in new_stack_objs[::-1]:
                try:
                    obj = self.resolve_object(objId)
                    self.log_print("    ETS: %s" % obj.describe())
                except AttributeError:
                    self.log_print("    ETS: [Unknown object %s]" % objId)
                    self.log_print(obj)
                    raise
        
        self.clean_deleted_objects(getattr(msg, "diffDeletedInstanceIds", []))
    
    def update_game_state_from_full(self, msg):
        self.game_state = msg.copy()
        self.zones = {}
        self.seat_to_hand = {}
        self.seat_to_library = {}
        self.seat_to_player = {}
        self.battlefield = None
        self.stack = None
        self.game_id =      msg.gameInfo.gameNumber
        self.super_format = msg.gameInfo.superFormat
        self.instance_to_game_object = {}
        self.register_turn_info(getattr(msg, "turnInfo", Obj()))
        self.register_zones(msg.zones)
        self.register_objects(getattr(msg, "gameObjects", []))
        self.register_players(msg.players)
        self.clean_deleted_objects(getattr(msg, "diffDeletedInstanceIds", []))
        self.handle_annotations(getattr(msg, "annotations", []))

    def register_turn_info(self, turnInfo):
        for (k, v) in turnInfo.__dict__.items():
            setattr(self.turn_info, k, v)
    
    def register_players(self, players):
        for player in players:
            # question to self: should I use systemSeatNumber or
            # controllerSeatId here?
            assert(player.controllerSeatId == player.systemSeatNumber)
            self.seat_to_player[player.controllerSeatId] = player
    
    def register_zones(self, zones):
        for zone in zones:
            self.zones[zone.zoneId] = zone
            if zone.type == "ZoneType_Hand":
                self.seat_to_hand[zone.ownerSeatId] = zone
            elif zone.type == "ZoneType_Library":
                self.seat_to_library[zone.ownerSeatId] = zone
            elif zone.type == "ZoneType_Battlefield":
                self.battlefield = zone
            elif zone.type == "ZoneType_Stack":
                self.stack = zone
                
    def track_original_name(self, game_object):
        object_id = game_object.instanceId
        try:
            zone = game_object.get_zone()
        except AttributeError:
            # .. huh
            return
        if not zone.type in ["ZoneType_Stack",
                             "ZoneType_Battlefield"]:
            return
        if not object_id in self.unique_ids and game_object.is_card():
            fresh_id = len(self.unique_objects) + 1
            self.unique_objects[fresh_id] = (
                game_object.ownerSeatId, game_object.get_name(), object_id)
            self.unique_ids[object_id] = fresh_id
    
    def register_objects(self, game_objects):
        for game_object in game_objects:
            self.instance_to_game_object[game_object.instanceId] = game_object
            self.track_original_name(game_object)

    def clean_deleted_objects(self, ids):
        for obj_id in ids:
            try:
                del self.instance_to_game_object[obj_id]
            except KeyError:
                pass

    def handle_annotations(self, annotations):
        for annotation in annotations:
            n_types = len(annotation.type)
            if n_types == 1:
                name = enum_name(annotation.type[0])
                method_name = "register_annotation_" + name
                if hasattr(self, method_name):
                    getattr(self, method_name)(annotation)
                else:
                    self.log_print("!!!!!!!!!!!!!!!!!!!! Ignoring annotation %s" % name, log_level=CRITICAL)

    ##########################################################################
    # annotation dispatch

    def register_annotation_revealedCardCreated(self, annotation):
        affected_id = annotation.affectedIds[0]
        affected = self.try_resolve_object(affected_id)
        self.log_print("    %s is revealed" % (
            "[%s]" % affected_id if affected is None else affected.describe())),

    def register_annotation_revealedCardDeleted(self, annotation):
        pass

    def register_annotation_attachment(self, annotation):
        pass

    def register_annotation_attachmentCreated(self, annotation):
        pass

    def register_annotation_attachmentDeleted(self, annotation):
        pass

    def register_annotation_objectsSelected(self, annotation):
        pass

    def register_annotation_resolutionComplete(self, annotation):
        pass

    def register_annotation_controllerChanged(self, annotation):
        # fixme i'd like to handle this but it seems that it emits the
        # change even if controller doesn't actually change (eg
        # with Trostani Discordant, all the time)
        pass

    def register_annotation_syntheticEvent(self, annotation):
        pass

    def register_annotation_lossOfGame(self, annotation):
        pass

    def register_annotation_counterAdded(self, annotation):
        pass

    def register_annotation_counterRemoved(self, annotation):
        pass

    def register_annotation_powerToughnessModCreated(self, annotation):
        pass

    def register_annotation_damageDealt(self, annotation):
        affector = self.try_resolve_object(annotation.affectorId)
        affected = self.try_resolve_object(annotation.affectedIds[0])
        self.log_print("    %s dealt %s damage to %s" % (affector.describe(),
                                                annotation.details.damage,
                                                affected.describe()))

    def register_annotation_modifiedPower(self, annotation):
        pass

    def register_annotation_modifiedToughness(self, annotation):
        pass

    def register_annotation_castingTimeOption(self, annotation):
        pass

    def register_annotation_modifiedLife(self, annotation):
        player = annotation.affectedIds[0]
        self.log_print("    P%s life total is now %s" % (
            player,
            getattr(self.seat_to_player[player], 'lifeTotal', 0)))

    def register_annotation_scry(self, annotation):
        affector_id = annotation.affectorId
        affector = self.try_resolve_object(affector_id)
        affected_id = annotation.affectedIds[0]
        affected = self.try_resolve_object(affected_id)
        self.log_print("    %s scries %s to the %s" % (
            affector.describe(),
            affected.describe() if affected else "[%s]" % affected_id,
            "bottom" if getattr(annotation.details, "topIds", None) is None else "top"))

    def register_annotation_linkInfo(self, annotation):
        pass

    def register_annotation_cardRevealed(self, annotation):
        pass

    def register_annotation_pendingEffect(self, annotation):
        pass

    def register_annotation_counter(self, annotation):
        pass

    def register_annotation_tokenCreated(self, annotation):
        pass

    def register_annotation_tokenDeleted(self, annotation):
        pass

    def register_annotation_gainDesignation(self, annotation):
        pass

    def register_annotation_designation(self, annotation):
        pass

    def register_annotation_shouldntPlay(self, annotation):
        pass

    def register_annotation_displayCardUnderCard(self, annotation):
        pass

    def register_annotation_qualification(self, annotation):
        pass

    def register_annotation_triggeringObject(self, annotation):
        pass

    def register_annotation_targetSpec(self, annotation):
        pass

    def register_annotation_addAbility(self, annotation):
        pass

    def register_annotation_removeAbility(self, annotation):
        pass

    def register_annotation_layeredEffectCreated(self, annotation):
        pass

    def register_annotation_layeredEffectDestroyed(self, annotation):
        pass

    def register_annotation_enteredZoneThisTurn(self, annotation):
        pass

    def register_annotation_abilityWordActive(self, annotation):
        pass

    def register_annotation_newTurnStarted(self, annotation):
        pass

    def register_annotation_phaseOrStepModified(self, annotation):
        pass

    def register_annotation_userActionTaken(self, annotation):
        pass

    def register_annotation_abilityInstanceCreated(self, annotation):
        pass

    def register_annotation_abilityInstanceDeleted(self, annotation):
        pass

    def register_annotation_miscContinuousEffect(self, annotation):
        pass

    def register_annotation_shuffle(self, annotation):
        player = self.resolve_object(self.resolve_object(annotation.affectorId).ownerSeatId)
        self.log_print("    %s shuffles deck" % player.describe())
        # nope, this is not right, or mtga has a huge derandomization hole
        # for old_id, new_id in zip(annotation.details.OldIds, annotation.details.NewIds):
        #     self.change_id(old_id, new_id)

    def register_annotation_tappedUntappedPermanent(self, annotation):
        pass

    def register_annotation_replacementEffect(self, annotation):
        pass

    def register_annotation_manaPaid(self, annotation):
        player = annotation.get_affector().get_controller().teamId
        color = annotation.details.color
        color_by_player = self.total_mana_spent.setdefault(player, {})
        color_by_player[color] = color_by_player.get(color, 0) + 1

    def register_annotation_resolutionStart(self, annotation):
        pass

    def change_id(self, old_id, new_id):
        self.id_change_map[new_id] = old_id
        if old_id in self.unique_ids:
            if new_id in self.unique_ids:
                del self.unique_objects[self.unique_ids[new_id]]
            self.unique_ids[new_id] = self.unique_ids[old_id]
        obj = self.try_resolve_object(old_id)
        self.log_print(crayons.black("      [%s] %sis now [%s]" % (
            old_id,
            "%s " % obj.get_name() if not obj is None else "",
            new_id), bold=True))

    def register_annotation_objectIdChanged(self, annotation):
        self.change_id(annotation.details.orig_id, annotation.details.new_id)
        # self.id_change_map[annotation.details.new_id] = annotation.details.orig_id
        # if annotation.details.orig_id in self.unique_ids:
        #     if annotation.details.new_id in self.unique_ids:
        #         del self.unique_objects[self.unique_ids[annotation.details.new_id]]
        #     self.unique_ids[annotation.details.new_id] = self.unique_ids[annotation.details.orig_id]
        # obj = self.try_resolve_object(annotation.details.orig_id)
        # self.log_print("      [%s] %sis now [%s]" % (
        #     annotation.details.orig_id,
        #     "%s " % obj.get_name() if not obj is None else "",
        #     annotation.details.new_id))

    def register_annotation_zoneTransfer(self, annotation):
        details  = annotation.details
        src      = self.zones[details.zone_src]
        dest     = self.zones[details.zone_dest]
        category = details.category

        st = enum_name(src.type)
        dt = enum_name(dest.type)

        def play_land():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.controllerSeatId
            self.log_print("    P%s plays %s%s" % (
                player, obj.describe(), src.describe_source("hand")))
        def draw_card():
            instanceId = annotation.affectedIds[0]
            obj = self.try_resolve_object(instanceId)
            player = dest.ownerSeatId
            self.log_print("    P%s draws a card%s" % (
                player, " (%s)" % obj.get_name() if obj else ""))
        def cast_spell():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = src.ownerSeatId
            annotation_source = src.describe_source("hand")
            self.log_print("    P%s casts a spell%s: %s" % (
                player, annotation_source, obj.get_name()))
        def object_resolves():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.ownerSeatId
            self.log_print("    P%s's %s resolves" % (
                player, obj.get_name()))
        def object_is_exiled():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.ownerSeatId
            self.log_print("    P%s's [%s] %s is exiled" % (
                player, instanceId, obj.get_name()))
        def object_is_destroyed():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.ownerSeatId
            self.log_print("    P%s's [%s] %s is destroyed%s" % (
                player, instanceId, obj.get_name(), dest.describe_destination("graveyard")))
        def object_is_legend_ruled():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.ownerSeatId
            self.log_print("    P%s's [%s] %s is put in %s because of legend rule" % (
                player, instanceId, obj.get_name(), dt))
        def object_etbs():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.ownerSeatId
            self.log_print("    P%s's [%s] %s goes to the battlefield from %s" % (
                player, instanceId, obj.get_name(), enum_name(src.type)))
        def puts_card_in_graveyard():
            affector_id = annotation.affectorId
            affector = "[%s]" % affector_id
            affected_id = annotation.affectedIds[0]
            affected = self.try_resolve_object(affected_id)
            if affected is None:
                affected = "[%s]" % affected_id
            else:
                affected = "[%s] %s" % (affected_id, affected.get_name())
            self.log_print("    %s puts %s in the graveyard" % (affector, affected))
        def surveils_to_graveyard():
            affector_id = annotation.affectorId
            affector = "[%s]" % affector_id
            affected_id = annotation.affectedIds[0]
            affected = self.try_resolve_object(affected_id)
            if affected is None:
                affected = "[%s]" % affected_id
            else:
                affected = "[%s] %s" % (affected_id, affected.get_name())
            self.log_print("    %s surveils %s to the graveyard" % (affector, affected))
        def puts_card_in_hand():
            affector_id = annotation.affectorId
            affector = "[%s]" % affector_id
            affected_id = annotation.affectedIds[0]
            affected = self.try_resolve_object(affected_id)
            if affected is None:
                affected = "[%s]" % affected_id
            else:
                affected = "[%s] %s" % (affected_id, affected.get_name())
            self.log_print("    %s puts %s in hand" % (affector, affected))
        def puts_card_in_library():
            affector_id = annotation.affectorId
            affector = self.resolve_object(affector_id)
            affected_id = annotation.affectedIds[0]
            affected = self.resolve_object(affected_id)
            self.log_print("    %s puts %s in owner's library" % (affector.describe(), affected.describe()))
        def exiles_card():
            affector_id = annotation.affectorId
            affector = "[%s]" % affector_id
            affected_id = annotation.affectedIds[0]
            affected = self.try_resolve_object(affected_id)
            if affected is None:
                affected = "[%s]" % affected_id
            else:
                affected = "[%s] %s" % (affected_id, affected.get_name())
            self.log_print("    %s exiles %s" % (affector, affected))
        def discards_card():
            affected_id = annotation.affectedIds[0]
            affected = self.try_resolve_object(affected_id)
            player = affected.ownerSeatId
            if affected is None:
                affected = "[%s]" % affected_id
            else:
                affected = "[%s] %s" % (affected_id, affected.get_name())
            self.log_print("    P%s discards %s" % (player, affected))
        def object_is_sacrificed():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.ownerSeatId
            self.log_print("    P%s's [%s] %s is sacrificed%s" % (
                player, instanceId, obj.get_name(), dest.describe_destination("graveyard")))
        def object_sba_damage():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.ownerSeatId
            self.log_print("    P%s's [%s] %s is dealt lethal damage%s" % (
                player, instanceId, obj.get_name(), dest.describe_destination("graveyard")))
        def object_sba_zero_toughness():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            player = obj.ownerSeatId
            self.log_print("    P%s's [%s] %s has zero toughness%s" % (
                player, instanceId, obj.get_name(), dest.describe_destination("graveyard")))
        def object_returns_to_hand():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            self.log_print("    %s returns to owner's hand" % (
                obj.describe()))
        def object_is_countered():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            self.log_print("    %s is countered%s" % (
                obj.describe(), dest.describe_destination("graveyard")))
        def object_fizzles():
            instanceId = annotation.affectedIds[0]
            obj = self.resolve_object(instanceId)
            self.log_print("    %s fizzles%s" % (
                obj.describe(), dest.describe_destination("graveyard")))
        
        def failed_match():
            msg = "!! Zone movement %s unparsed: %s -> %s (%s)" % (
                annotation.id,
                st, dt, category)
            self.log_print("!!!!%s" % msg, log_level=CRITICAL)
            self.log_print(annotation)
            
        dispatch_table = [
            (("*", "battlefield", "PlayLand"), play_land),
            (("*", "stack", "CastSpell"), cast_spell),
            (("*", "hand", "Draw"), draw_card),
            (("stack", "*", "Resolve"), object_resolves),
            (("stack", "*", "nil"), object_fizzles),
            (("stack", "*", "Countered"), object_is_countered),
            (("battlefield", "*", "Exile"), object_is_exiled),
            (("battlefield", "*", "Destroy"), object_is_destroyed),
            (("*", "battlefield", "*"), object_etbs),
            (("*", "graveyard", "Put"), puts_card_in_graveyard),
            (("*", "library", "Put"), puts_card_in_library),
            (("*", "hand", "Put"), puts_card_in_hand), 
            (("*", "exile", "Exile"), exiles_card),
            (("hand", "graveyard", "*"), discards_card),
            (("battlefield", "graveyard", "SBA_LegendRule"), object_is_legend_ruled),
            (("battlefield", "*", "Sacrifice"), object_is_sacrificed),
            (("battlefield", "*", "SBA_ZeroToughness"), object_sba_zero_toughness),
            (("battlefield", "*", "SBA_Damage"), object_sba_damage),
            (("battlefield", "*", "SBA_ZeroLoyalty"), object_sba_damage),
            (("*", "hand", "Return"), object_returns_to_hand),
            (("library", "graveyard", "Surveil"), surveils_to_graveyard),
            (("*", "*", "*"), failed_match)
            ]
            
        for ((m_src, m_dest, m_cat), call) in dispatch_table:
            if (m_src == "*"  or m_src == st)  and \
               (m_dest == "*" or m_dest == dt) and \
               (m_cat == "*"  or m_cat == category):
                try:
                    return call()
                except:
                    self.log_print("Annotation raised exception", log_level=CRITICAL)
                    self.log_print(annotation, log_level=CRITICAL)
                    raise
        
    ##########################################################################
    # message dispatch
    
    def handle_greToClientMessage(self, msg):
        if msg.type == "GREMessageType_DieRollResultsResp":
            self.die_roll_winner = sorted(
                msg.dieRollResultsResp.playerDieRolls,
                key=lambda m: -getattr(m, "rollValue", 0))[0].systemSeatId
            self.log_print("  Die roll winner: %s" % self.seat_to_player_config[self.die_roll_winner].playerName)
        elif msg.type == "GREMessageType_QueuedGameStateMessage" or \
             msg.type == "GREMessageType_GameStateMessage":
            if msg.gameStateMessage.type == "GameStateType_Diff":
                self.update_game_state_from_diff(msg.gameStateMessage)
            elif msg.gameStateMessage.type == "GameStateType_Full":
                self.update_game_state_from_full(msg.gameStateMessage)
            if hasattr(msg.gameStateMessage, "gameInfo") and \
                   msg.gameStateMessage.gameInfo.matchState == "MatchState_GameComplete":
                result = msg.gameStateMessage.gameInfo.results[0]
                self.game_winner = result.winningTeamId
                assert(self.seat_to_player[self.game_winner].teamId ==
                       self.seat_to_player[self.game_winner].systemSeatNumber)
                self.log_print("\n  P%s (%s) wins the game (Reason: %s)" % (
                    self.game_winner,
                    self.seat_to_player_config[self.game_winner].playerName,
                    result.reason.split("_")[1]))
    
    def handle_greToClientEvent(self, event):
        for msg in event.greToClientMessages:
            self.handle_greToClientMessage(msg)

    ##########################################################################
    # drivers
    
    def analyze(self):
        with open(logfile, "rb") as f:
            e = self.events[0].read_entry(f)
            if e.ClientToMatchServiceMessageType != 4:
                raise Exception("Probably the wrong message..")
            self.our_id = e.Payload.ClientId
            self.our_name = e.Payload.PlayerName
            self.timestamp = e.Timestamp
            for event in self.events[1:]:
                if event.id[2] == "MatchGameRoomStateChangedEvent":
                    entry = event.read_entry(f).matchGameRoomStateChangedEvent
                    self.handle_matchGameRoomStateChangedEvent(entry)
                elif event.id[2] == "GreToClientEvent":
                    entry = event.read_entry(f).greToClientEvent
                    self.handle_greToClientEvent(entry)

    def stream_analyze(self):
        e = next(self.events).read_entry()
        if e.ClientToMatchServiceMessageType != 4:
            raise Exception("Probably the wrong message..")
        self.our_id = e.Payload.ClientId
        self.our_name = e.Payload.PlayerName
        self.timestamp = e.Timestamp
        for event in self.events:
            if event.id[2] == "MatchGameRoomStateChangedEvent":
                entry = event.read_entry().matchGameRoomStateChangedEvent
                self.handle_matchGameRoomStateChangedEvent(entry)
            elif event.id[2] == "GreToClientEvent":
                entry = event.read_entry().greToClientEvent
                self.handle_greToClientEvent(entry)
        print("self.events stream finished.")
    # def win(self):
    #     we_won = self.seat_to_player[self.game_winner].userId == self.our_id
    #     return 1 if we_won else 0

##############################################################################
    
def build_index_file(f):
    block_start = None
    calls = []
    returns = []
    gre_blocks = []
    games = []
    matches = []

    def start_match():
        nonlocal gre_blocks
        nonlocal games
        gre_blocks = []
        games = []

    def end_match():
        games.append(gre_blocks)
        matches.append(games)

    def client_gre_block_started(header, start_position, first_line):
        if first_line[0] == "{":
            last_line = "}"
        elif first_line[0] == "[":
            last_line = "]"
        else:
            raise Exception("Don't know how to handle first line %s" % repr(first_line))

        def handle_block_end(l):
            if l[0] == last_line:
                gre_blocks.append(LogEntry(header, start_position, f.tell()))
                return True
            return False
        return handle_block_end

    def default_end_handler(l):
        return False

    end_handler = default_end_handler
    while True:
        current_position = f.tell()
        l = f.readline().decode("ascii")
        ls = l.strip()
        if end_handler(l):
            end_handler = default_end_handler
        elif l == "":
            break
        elif l.startswith("[Client GRE]"):
            if "WebSocketClient" in l:
                start_match()
                continue
            l = l.strip().split()
            client_gre_header = (l[-4], l[-2][:-1], l[-1])
            block_start = f.tell()
            l = f.readline().decode("ascii")
            if "GREConnection.HandleWebSocketClosed" in l: # skip the disconnection announcement
                continue
            end_handler = client_gre_block_started(client_gre_header, block_start, l)
        elif l.startswith("==>"):
            block_type = "call"
            block_start = f.tell()
            block_name = l.strip()[4:-1]
        elif l.startswith("<=="):
            block_type = "return"
            block_start = f.tell()
            block_name = l.strip()[4:]
        elif l.startswith("[UnityCrossThreadLogger]STATE CHANGED") and \
             ls.endswith("MatchCompleted"):
            end_match()
        elif l.startswith("[UnityCrossThreadLogger]") and block_start is not None:
            if block_type == "call":
                calls.append(LogEntry(block_name, block_start, current_position))
            elif block_type == "return":
                returns.append(LogEntry(block_name, block_start, current_position))
            block_start = None
        else:
            pass
    calls = dict((call.call_id(), call) for call in calls)
    calls_and_returns = dict((r.call_id(), (calls[r.call_id()], r)) for r in returns)

    return { "matches": matches,
             "calls_and_returns": calls_and_returns }

##############################################################################

class StreamingLogEntry:
    def __init__(self, header, obj):
        self.id = header
        self.obj = obj
    def read_entry(self):
        return self.obj

class EventHandler:
    def __init__(self, event_queue, sf):
        self.q = event_queue
        self.sf = sf
    def new_match(self):
        print("Match started!")
    def match_over(self):
        print("Match over!")
        self.q.put(None)
    def new_gre_block(self, header, lines):
        # print("EventHandler sees new block!")
        # print("Header: ", header)
        lines = "".join(lines)
        obj = mtga_log_object.json_to_obj(json.loads(lines))
        self.q.put(StreamingLogEntry(header, obj))

# pass the streaming file to this
def build_streaming_index(f, event_handler, box_stop):
    block_start = None

    def start_match():
        event_handler.new_match()

    def end_match():
        event_handler.match_over()

    def client_gre_block_started(header, first_line):
        lines = [first_line]
        
        if first_line[0] == "{":
            last_line = "}"
        elif first_line[0] == "[":
            last_line = "]"
        else:
            raise Exception("Don't know how to handle first line %s" % repr(first_line))

        def handle_block_end(l):
            lines.append(l)
            if l[0] == last_line:
                event_handler.new_gre_block(header, lines)
                return True
            return False
        return handle_block_end

    def default_end_handler(l):
        return False

    end_handler = default_end_handler
    while box_stop[0]:
        l = f.readline()
        ls = l.strip()
        if end_handler(l):
            end_handler = default_end_handler
        elif l == "":
            break
        elif l.startswith("[Client GRE]"):
            if "WebSocketClient" in l:
                start_match()
                continue
            l = l.strip().split()
            client_gre_header = (l[-4], l[-2][:-1], l[-1])
            l = f.readline()
            if "GREConnection.HandleWebSocketClosed" in l: # skip the disconnection announcement
                continue
            end_handler = client_gre_block_started(client_gre_header, l)
        elif l.startswith("[UnityCrossThreadLogger]STATE CHANGED") and \
             ls.endswith("MatchCompleted"):
            end_match()
        else:
            pass

##############################################################################

class MTGALogReader:
    def __init__(self, f):
        self.index = build_index_file(f)
    def analyze_game(self, match, game, log_level=5):
        result = GameAnalysis(self.index["matches"][match][game], log_level=log_level)
        register_current_game(result)
        result.analyze()
        return result
    def read_block(self, i):
        def stubborn_parse_block(s):
            sl = s.split("\n")
            while len(sl) > 0:
                sl.pop()
                try:
                    p = json.loads("\n".join(sl))
                    print("Hey, stubborn parse worked!")
                    return p
                except json.decoder.JSONDecodeError:
                    continue
            print("Stubborn parse failed...")
            return s
        def read_log_entry(f, index_entry):
            start, end, _ = index_entry
            f.seek(start)
            return f.read(end - start).decode("ascii")
        with open(logfile, "rb") as f:
            index_entry = self.index[i]
            call = read_log_entry(f, index_entry[0])
            ret = read_log_entry(f, index_entry[1])
            try:
                call = json.loads(call)
            except json.decoder.JSONDecodeError:
                if call[0] == "[" or call[0] == "]":
                    print("Weird, this looks like a json call. Let's try stripping lines from the back")
                    call = stubborn_parse_block(call)
                else:
                    pass
            try:
                ret = json.loads(ret)
            except json.decoder.JSONDecodeError:
                if ret[0] == "[" or ret[0] == "]":
                    print("Weird, this looks like a json call. Let's try stripping lines from the back")
                    ret = stubborn_parse_block(ret)
                else:
                    pass
            return call, ret, index_entry[0][2], index_entry[1][2]
    def block_names(self):
        for k in self.index:
            print(self.index[k][0][2], self.index[k][1][2])
        
# try:
#     with open(pickle_file, "rb") as f:
#         log = pickle.load(f)
# except EOFError:
#     print("Bad pickle file, recreating")
#     with open(pickle_file, "wb") as f:
#         log = MTGALogReader()
#         pickle.dump(log, f)
# except FileNotFoundError:
#     print("Pickle file not found, recreating")
#     with open(pickle_file, "wb") as f:
#         log = MTGALogReader()
#         pickle.dump(log, f)

# log = MTGALogReader(open(logfile, "rb"))

##############################################################################

import queue
import streaming_file
import colorama
import crayons

colorama.init()

class QueueIterator:
    def __init__(self, q):
        self.q = q
    def __iter__(self):
        return self
    def __next__(self):
        result = self.q.get()
        if result is None:
            raise StopIteration
        return result

def watch_game():
    logging.debug("Creating streaming_file")
    sf = streaming_file.stream_file_contents(logfile)
    logging.debug("Creating event_queue")
    event_queue = queue.Queue()
    logging.debug("Creating event handler")
    handler = EventHandler(event_queue, sf)
    logging.debug("Calling build_streaming_index")

    box_stop = [True]
    def bsi():
        build_streaming_index(sf, handler, box_stop)
    bsi_thread = threading.Thread(target=bsi)
    bsi_thread.start()

    logging.debug("Starting streaming analysis...")
    game = GameAnalysis(QueueIterator(event_queue))
    register_current_game(game)
    game.stream_analyze()
    logging.debug("Stream analysis done.")

    box_stop[0] = False
    sf.stop_box[0] = False

    mdb = metagame_db.MetagameDB()
    if mdb.record_game(game.game_record()):
        logging.debug("Wrote game into database")
    else:
        logging.debug("Game was not written into database")
    
if __name__ == '__main__':
    logging.basicConfig(filename='mtga-watch.log', level=logging.DEBUG)
    logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    while True:
        watch_game()

"""
Subject: CARLA, Fanatec-CSL~series Integration
Author: CARLA-dev, Arjun Joshi
Recent Date: 05.25.2025
Versioning: v0.1.42 (Fixed Font, Vector2D, and LaneMarkingType)
OS: Windows 11 Enterprise x64
CARLA Release: 0.9.15 ["UE4-dev","Latest"], Unreal Engine 4 PhysEngine
https://github.com/carla-simulator/carla/tree/ue4-dev?tab=readme-ov-file
"""


# I SHOULD BE ABLE TO DO THIS ON LINUX AND WILL BE PURSUING THIS ISSUE AFTER THE DEMO. #

#####
# In-depth info at end of script.

#----TL;DR----
#- Integration of Fanatec CSL-series kit with CARLA using [carla,pygame] python package & CARLA PythonAPI
#- Script includes World, Control, HUD, Text, sensor, camera, game loop classes & main function.
#- Detailed description below. Some important stuff about unique mapping configurations.

#- DATA TRANSFORMATION: Controller Inputs are read, transformed into usable values by CARLA, passed via API. See workflow document.
#-         SCREEN VIEW: No native CARLA "dashboard" view. Class introduced below.
#-      SCENARIO SETUP: NO OTHER ACTIVE ACTORS. Scenarios and custom maps require separate script
#  
# Mapping utility is in a separate script and tricky/finicky. 
#-------------
# Notes:
# - Playstation controls are temporarily mapped to input; Fanatec mappings remain commented out (see DualControl class)




# Import Packages, Locate CARLA packages
from __future__ import print_function
import glob
import os
import sys
import subprocess # ADDED: For launching CARLA server
import time       # ADDED: For delays

# try # Original CARLA path appending - typically handled by CARLA_PATH environment variable
#     sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg') % (
#         sys.version_info.major,
#         sys.version_info.minor,
#         'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0]
# except IndexError:
#     pass

import carla
#
from carla import ColorConverter as cc
#
import argparse
import collections
import datetime
import logging
import math
import random
import re
import weakref

try:
    import pygame
#  Keyboard (pygame.locals): Keep from old script for HUD
    from pygame.locals import KMOD_CTRL
    from pygame.locals import KMOD_SHIFT
    from pygame.locals import K_0
    from pygame.locals import K_9
    from pygame.locals import K_BACKQUOTE
    from pygame.locals import K_BACKSPACE
    from pygame.locals import K_COMMA
    from pygame.locals import K_DOWN
    from pygame.locals import K_ESCAPE
    from pygame.locals import K_F1
    from pygame.locals import K_LEFT
    from pygame.locals import K_PERIOD
    from pygame.locals import K_RIGHT
    from pygame.locals import K_SLASH
    from pygame.locals import K_SPACE
    from pygame.locals import K_TAB
    from pygame.locals import K_UP
    from pygame.locals import K_a
    from pygame.locals import K_c
    from pygame.locals import K_d
    from pygame.locals import K_h
    from pygame.locals import K_m
    from pygame.locals import K_p
    from pygame.locals import K_q
    from pygame.locals import K_r
    from pygame.locals import K_s
    from pygame.locals import K_w
except ImportError:
    raise RuntimeError('cannot import pygame, make sure pygame package is installed')

try:
    import numpy as np
except ImportError:
    raise RuntimeError('cannot import numpy, make sure numpy package is installed')

# Global variable to hold the CARLA server process
carla_server_process = None

# +------------------------------------------------------------------------------+
# | Scoring Constants                                                            |
# +------------------------------------------------------------------------------+
INITIAL_SCORE = 1000
COLLISION_PENALTY = 15
LANE_VIOLATION_PENALTY = 5 # Base penalty for minor lane issues
ONCOMING_TRAFFIC_PENALTY_MULTIPLIER = 3 # Multiply base for oncoming
SOLID_LINE_CROSSING_PENALTY_MULTIPLIER = 1.5 # Multiply base for solid line
COLLISION_COOLDOWN_SECONDS = 2.0 # Seconds between collision penalties

# +------------------------------------------------------------------------------+
# | Global Functions                                                             |
# +------------------------------------------------------------------------------+



def find_weather_presets():
    rgx = re.compile('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)')
    name = lambda x: ' '.join(m.group(0) for m in rgx.finditer(x))
    presets = [x for x in dir(carla.WeatherParameters) if re.match('[A-Z].+', x)]
    return [(getattr(carla.WeatherParameters, x), name(x)) for x in presets]


def get_actor_display_name(actor, truncate=250):
    name = ' '.join(actor.type_id.replace('_', '.').title().split('.')[1:])
    return (name[:truncate - 1] + u'\u2026') if len(name) > truncate else name


# +------------------------------------------------------------------------------+
# | World Class                                                                  |
# +------------------------------------------------------------------------------+


class World(object):
    def __init__(self, carla_world, hud, actor_filter, fov): # MODIFIED: Added fov argument
        self.world = carla_world
        self.hud = hud
        self.player = None
        self.collision_sensor = None
        self.lane_invasion_sensor = None
        self.gnss_sensor = None
        self.camera_manager = None
        self._weather_presets = find_weather_presets()
        self._weather_index = 0
        self._actor_filter = actor_filter
        self.fov = fov  # ADDED: Store fov
        self.restart()
        self.world.on_tick(hud.on_world_tick)

    def restart(self):
        # Keep same camera config if the camera manager exists.
        cam_index = self.camera_manager.index if self.camera_manager is not None else 0
        cam_pos_index = self.camera_manager.transform_index if self.camera_manager is not None else 0
        
        ##### Spawn a new player vehicle - CHOICE or RANDOM
        blueprint = self.world.get_blueprint_library().find('vehicle.mercedes.sprinter')
        #blueprint = random.choice(self.world.get_blueprint_library().filter(self._actor_filter))
        blueprint.set_attribute('role_name', 'hero') 
        if blueprint.has_attribute('color'):
            color = random.choice(blueprint.get_attribute('color').recommended_values)
            blueprint.set_attribute('color', color)
        
        if self.player is not None:
            spawn_point = self.player.get_transform()
            spawn_point.location.z += 2.0
            spawn_point.rotation.roll = 0.0
            spawn_point.rotation.pitch = 0.0
            self.destroy() # Destroys old player and its sensors
            self.player = self.world.try_spawn_actor(blueprint, spawn_point)
        
        while self.player is None:
            spawn_points = self.world.get_map().get_spawn_points()
            spawn_point = random.choice(spawn_points) if spawn_points else carla.Transform()
            self.player = self.world.try_spawn_actor(blueprint, spawn_point)

        if isinstance(self.player, carla.Vehicle):
            self.player.set_autopilot(False)

        # Reset HUD which also resets scores and sensor counts within HUD
        self.hud.reset() 

        # Set up the sensors for the new player
        self.collision_sensor = CollisionSensor(self.player, self.hud)
        self.lane_invasion_sensor = LaneInvasionSensor(self.player, self.hud)
        self.gnss_sensor = GnssSensor(self.player)
        # MODIFIED: Pass fov to CameraManager
        self.camera_manager = CameraManager(self.player, self.hud, self.fov) 
        self.camera_manager.transform_index = cam_pos_index
        self.camera_manager.set_sensor(cam_index, notify=False)
        
        actor_type = get_actor_display_name(self.player)
        self.hud.notification(f"{actor_type} Ready!")


    def next_weather(self, reverse=False):
        self._weather_index += -1 if reverse else 1
        self._weather_index %= len(self._weather_presets)
        preset = self._weather_presets[self._weather_index]
        self.hud.notification('Weather: %s' % preset[1])
        self.player.get_world().set_weather(preset[0])

    def tick(self, clock):
        self.hud.tick(self, clock)
        if self.player is not None and isinstance(self.player, carla.Vehicle):
            spectator = self.world.get_spectator()
            vehicle_transform = self.player.get_transform()
            
            driver_seat_offset_location = carla.Location(x=0.8, y=-0.4, z=1.3) # Adjusted for a more typical driver view

            # Apply the vehicle's rotation to the offset vector using transform_vector
            rotated_offset = vehicle_transform.transform_vector(driver_seat_offset_location)
            # Add the rotated offset vector to the vehicle's world location
            spectator_location = vehicle_transform.location + rotated_offset
            # Create the spectator transform using the new location and the vehicle's rotation
            # The rotation is set to the vehicle's rotation to always look forward from the driver's perspective
            spectator_transform = carla.Transform(spectator_location, vehicle_transform.rotation)
            
            spectator.set_transform(spectator_transform)

    def render(self, display):
        if self.camera_manager: self.camera_manager.render(display)
        if self.hud: self.hud.render(display)

    def destroy(self):
        sensors = [
            self.camera_manager.sensor if self.camera_manager else None,
            self.collision_sensor.sensor if self.collision_sensor else None,
            self.lane_invasion_sensor.sensor if self.lane_invasion_sensor else None,
            self.gnss_sensor.sensor if self.gnss_sensor else None]
        for sensor in sensors:
            if sensor is not None:
                sensor.stop()
                sensor.destroy()
        if self.player is not None:
            self.player.destroy()
            self.player = None # Important to nullify after destruction

        # Nullify sensor object references
        self.collision_sensor = None
        self.lane_invasion_sensor = None
        self.gnss_sensor = None
        self.camera_manager = None


# +------------------------------------------------------------------------------+
# | DualControl Class                                                            |
# +------------------------------------------------------------------------------+

class DualControl(object):
    def __init__(self, world, start_in_autopilot):
        self._autopilot_enabled = start_in_autopilot
        if isinstance(world.player, carla.Vehicle):
            self._control = carla.VehicleControl()
            world.player.set_autopilot(False) # Ensure autopilot is off initially for manual control
        elif isinstance(world.player, carla.Walker):
            self._control = carla.WalkerControl()
            self._autopilot_enabled = False
            self._rotation = world.player.get_transform().rotation
        else:
            raise NotImplementedError("Actor type not supported")
        self._steer_cache = 0.0 

        world.hud.notification("Press 'H' or '?' for help.", seconds=4.0)

        pygame.joystick.init()
        joystick_count = pygame.joystick.get_count()
        if joystick_count == 0:
            # Allow keyboard-only mode if no joysticks are found.
            print("Warning: No joysticks found. Fanatec/joystick input will be disabled. Using keyboard only.")
            self._steer_joystick = None
            self._pedal_joystick = None
        else:
            print(f"Found {joystick_count} joystick(s).")
            
            self._steer_joystick_idx = 1 
            self._pedal_joystick_idx = 1 
            
            self._steer_axis_idx = 0      
            self._throttle_axis_idx = 2   
            self._brake_axis_idx = 3      
            
            self._handbrake_button_idx = 0 
            self._reverse_button_idx = 1   
            self._gear_up_button_idx = 4   
            self._gear_down_button_idx = 5 
            self._gear_mode_manual = 2     


            try:
                if self._steer_joystick_idx < joystick_count:
                    self._steer_joystick = pygame.joystick.Joystick(self._steer_joystick_idx)
                    self._steer_joystick.init()
                    print(f"Steering/Primary Joystick {self._steer_joystick_idx}: {self._steer_joystick.get_name()}")
                else:
                    print(f"Warning: Steering joystick index {self._steer_joystick_idx} is out of range ({joystick_count} joysticks found, max index {joystick_count-1}). Joystick input disabled.")
                    self._steer_joystick = None
                    self._pedal_joystick = None 


                if self._pedal_joystick_idx != self._steer_joystick_idx: 
                    if self._pedal_joystick_idx < joystick_count:
                        self._pedal_joystick = pygame.joystick.Joystick(self._pedal_joystick_idx)
                        self._pedal_joystick.init()
                        print(f"Pedal Joystick {self._pedal_joystick_idx}: {self._pedal_joystick.get_name()}")
                    else:
                        print(f"Warning: Pedal joystick index {self._pedal_joystick_idx} is out of range ({joystick_count} joysticks found, max index {joystick_count-1}). Pedal input via this joystick disabled.")
                        self._pedal_joystick = None 
                elif self._steer_joystick: 
                    self._pedal_joystick = self._steer_joystick

            except pygame.error as e:
                print(f"Error initializing joystick: {e}. Joystick input will be disabled.")
                self._steer_joystick = None
                self._pedal_joystick = None


        self._steer_deadzone = 0.05  
        self._pedal_deadzone = 0.02  
        self._steer_linearity = 0.32 


    def parse_events(self, world, clock):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            elif event.type == pygame.KEYUP:
                if self._is_quit_shortcut(event.key):
                    return True
                elif event.key == K_BACKSPACE:
                    world.restart()
                elif event.key == K_F1:
                    world.hud.toggle_info()
                elif event.key == K_h or (event.key == K_SLASH and pygame.key.get_mods() & KMOD_SHIFT):
                    world.hud.help.toggle()
                elif event.key == K_TAB:
                    if world.camera_manager: world.camera_manager.toggle_camera()
                elif event.key == K_c and pygame.key.get_mods() & KMOD_SHIFT:
                    world.next_weather(reverse=True)
                elif event.key == K_c:
                    world.next_weather()
                elif event.key == K_BACKQUOTE:
                    if world.camera_manager: world.camera_manager.next_sensor()
                elif event.key > K_0 and event.key <= K_9: 
                    if world.camera_manager: world.camera_manager.set_sensor(event.key - K_0 -1) 
                elif event.key == K_r:
                    if world.camera_manager: world.camera_manager.toggle_recording()
                if isinstance(self._control, carla.VehicleControl) and world.player:
                    if event.key == K_q: 
                        current_control = world.player.get_control()
                        if current_control.gear == -1 : 
                             self._control.gear = 1 
                             self._control.reverse = False
                        else:
                            self._control.gear = -1 
                            self._control.reverse = True
                    elif event.key == K_m:
                        self._control.manual_gear_shift = not self._control.manual_gear_shift
                        current_player_control = world.player.get_control() 
                        self._control.gear = current_player_control.gear if current_player_control else self._control.gear 
                        world.hud.notification('%s Transmission' %
                                            ('Manual' if self._control.manual_gear_shift else 'Automatic'))
                    elif self._control.manual_gear_shift and event.key == K_COMMA: 
                        self._control.gear = max(-1, self._control.gear - 1)
                    elif self._control.manual_gear_shift and event.key == K_PERIOD: 
                        self._control.gear = self._control.gear + 1
                    elif event.key == K_p:
                        self._autopilot_enabled = not self._autopilot_enabled
                        world.player.set_autopilot(self._autopilot_enabled)
                        world.hud.notification('Autopilot %s' % ('On' if self._autopilot_enabled else 'Off'))

            elif event.type == pygame.JOYBUTTONDOWN:
                if self._steer_joystick is None: continue

                if event.joy == self._steer_joystick_idx: 
                    pass 

                if isinstance(self._control, carla.VehicleControl) and world.player:
                    if event.joy == self._steer_joystick_idx and event.button == self._handbrake_button_idx:
                        self._control.hand_brake = not self._control.hand_brake 
                        world.hud.notification('Handbrake %s' % ('On' if self._control.hand_brake else 'Off'))

                    if event.joy == self._steer_joystick_idx and event.button == self._reverse_button_idx:
                        player_velocity = world.player.get_velocity().length() if world.player else 0
                        if self._control.gear == -1: 
                            self._control.gear = 1 if player_velocity > 0.1 else 0 
                            self._control.reverse = False
                            world.hud.notification('Gear: D' if self._control.gear == 1 else 'Gear: N')
                        else: 
                            self._control.gear = -1 
                            self._control.reverse = True
                            world.hud.notification('Gear: R')

                    if event.joy == self._steer_joystick_idx and event.button == self._gear_mode_manual:
                        self._control.manual_gear_shift = not self._control.manual_gear_shift
                        current_player_control = world.player.get_control()
                        self._control.gear = current_player_control.gear if current_player_control else self._control.gear 
                        world.hud.notification('%s Transmission' % ('Manual' if self._control.manual_gear_shift else 'Automatic'))

                    if self._control.manual_gear_shift and event.joy == self._steer_joystick_idx and event.button == self._gear_up_button_idx:
                        self._control.gear = self._control.gear + 1 
                        world.hud.notification('Gear: %s' % self._control.gear)

                    if self._control.manual_gear_shift and event.joy == self._steer_joystick_idx and event.button == self._gear_down_button_idx:
                        self._control.gear = max(-1, self._control.gear - 1) 
                        world.hud.notification('Gear: %s' % {-1: 'R', 0: 'N'}.get(self._control.gear, str(self._control.gear)))


        if not self._autopilot_enabled and world.player:
            if isinstance(self._control, carla.VehicleControl):
                if self._steer_joystick: 
                    self._parse_vehicle_wheel()
                else: 
                    self._parse_vehicle_keys(pygame.key.get_pressed(), clock.get_time())
            elif isinstance(self._control, carla.WalkerControl):
                self._parse_walker_keys(pygame.key.get_pressed(), clock.get_time()) 
            world.player.apply_control(self._control)

    def _parse_vehicle_keys(self, keys, milliseconds):
        """Parses keyboard input for vehicle control."""
        self._control.throttle = 1.0 if keys[K_UP] or keys[K_w] else 0.0
        steer_increment = 5e-4 * milliseconds 
        if keys[K_LEFT] or keys[K_a]:
            self._steer_cache -= steer_increment
        elif keys[K_RIGHT] or keys[K_d]:
            self._steer_cache += steer_increment
        else:
            self._steer_cache = 0.0 
        self._steer_cache = min(0.7, max(-0.7, self._steer_cache)) 
        self._control.steer = round(self._steer_cache, 1)
        self._control.brake = 1.0 if keys[K_DOWN] or keys[K_s] else 0.0
        self._control.hand_brake = keys[K_SPACE]


    def _parse_vehicle_wheel(self):
        if not self._steer_joystick or not self._pedal_joystick:
            self._control.steer = 0.0
            self._control.throttle = 0.0
            self._control.brake = 0.0
            return

        try:
            raw_steer = self._steer_joystick.get_axis(self._steer_axis_idx)
            raw_throttle = self._pedal_joystick.get_axis(self._throttle_axis_idx) 
            raw_brake = self._pedal_joystick.get_axis(self._brake_axis_idx)       

        except pygame.error as e:
            print(f"Error reading joystick axis: {e}")
            raw_steer, raw_throttle, raw_brake = 0.0, 1.0, 1.0 
            if self._throttle_axis_idx == 4 and self._brake_axis_idx == 3: 
                 raw_throttle, raw_brake = -1.0, -1.0


        steer_cmd = raw_steer
        if abs(steer_cmd) < self._steer_deadzone:
            steer_cmd = 0.0
        else:
            sign = 1 if steer_cmd > 0 else -1
            scaled_steer = (abs(steer_cmd) - self._steer_deadzone) / (1.0 - self._steer_deadzone)
            steer_cmd = sign * math.pow(scaled_steer, self._steer_linearity if self._steer_linearity > 0 else 1.0)

        """     ############ NEEDS TO BE FIXED WHEN ATTACHED TO FANATEC

        if self._throttle_axis_idx == 4 and self._brake_axis_idx == 3: 
            throttle_cmd = (raw_throttle + 1.0) / 2.0
            brake_cmd = (raw_brake + 1.0) / 2.0
        else: 
            throttle_cmd = (1.0 - raw_throttle) / 2.0  
            brake_cmd = (1.0 - raw_brake) / 2.0        
"""
###################################################################################
        throttle_cmd = raw_throttle
        brake_cmd = raw_brake
###################################################################################
        if throttle_cmd < self._pedal_deadzone: throttle_cmd = 0.0
        if brake_cmd < self._pedal_deadzone: brake_cmd = 0.0
        
        self._control.steer = max(-1.0, min(1.0, steer_cmd))
        self._control.throttle = max(0.0, min(1.0, throttle_cmd))
        self._control.brake = max(0.0, min(1.0, brake_cmd))


    def _parse_walker_keys(self, keys, milliseconds):
        self._control.speed = 0.0
        if keys[K_DOWN] or keys[K_s]: self._control.speed = 0.0 
        if keys[K_LEFT] or keys[K_a]:
            self._control.speed = .01 
            self._rotation.yaw -= 0.08 * milliseconds
        if keys[K_RIGHT] or keys[K_d]:
            self._control.speed = .01 
            self._rotation.yaw += 0.08 * milliseconds
        if keys[K_UP] or keys[K_w]:
            self._control.speed = 5.556 if pygame.key.get_mods() & KMOD_SHIFT else 2.778 
        self._control.jump = keys[K_SPACE]
        self._rotation.yaw = round(self._rotation.yaw, 1)
        self._control.direction = self._rotation.get_forward_vector()

    @staticmethod
    def _is_quit_shortcut(key):
        return (key == K_ESCAPE) or (key == K_q and pygame.key.get_mods() & KMOD_CTRL)

# +------------------------------------------------------------------------------+
# | HUD Class (MODIFIED)                                                         |
# +------------------------------------------------------------------------------+

class HUD(object):
    def __init__(self, width, height, args): # Added args to __init__
        self.dim = (width, height)
        self._notification_font = pygame.font.Font(pygame.font.get_default_font(), 20)

        # Custom Font Path (relative to script execution, assuming carla_root is the base)
        self.custom_notification_font_path = os.path.join(args.carla_root, 'CarlaUE4', 'Content', 'Carla', 'Fonts', 'RaceHead.ttf') # Corrected font path and name
        self._use_custom_notification_font = False
        try:
            if os.path.exists(self.custom_notification_font_path):
                # Test loading it to ensure it's a valid font file
                pygame.font.Font(self.custom_notification_font_path, 1) # Test load with dummy size
                self._use_custom_notification_font = True
                print(f"Successfully located and will use custom font: {self.custom_notification_font_path}")
            else:
                print(f"Warning: Custom font file '{self.custom_notification_font_path}' not found. Falling back to default fonts for notifications.")
        except Exception as e:
            print(f"Error loading custom font '{self.custom_notification_font_path}': {e}. Falling back to default fonts for notifications.")
        
        primary_font_size = 28
        secondary_font_size = 20 
        score_font_size = 36    
        
        primary_font_names = ['arial', 'verdana', 'dejavusans', 'sans']
        secondary_font_names = ['ubuntumono', 'consolas', 'courier', 'mono']

        chosen_primary_font_name = self._find_font(primary_font_names, bold=True)
        self._font_primary_hud = pygame.font.Font(chosen_primary_font_name, primary_font_size)
        
        chosen_secondary_font_name = self._find_font(secondary_font_names, bold=True)
        self._font_secondary_hud = pygame.font.Font(chosen_secondary_font_name, secondary_font_size)
        
        self._font_score_hud = pygame.font.Font(self._find_font(primary_font_names, bold=True), score_font_size) 

        # MODIFIED: Sound Management
        pygame.mixer.init() 
        self.sounds = {}
        self.sound_cooldowns = {
            "lane_drift": 3.0, # Crossing broken lines
            "solid_line_crossing": 2.0, # Crossing solid line, same direction
            "oncoming_traffic_violation": 1.0, # More frequent for severe
            "lane_violation_unknown": 3.0, # Generic if details unknown
            "speeding": 5.0,
            "collision": 0.0, # Penalty cooldown is handled by CollisionSensor, sound plays per penalty
            "error": 0.0, # Errors play immediately
            "default_notification": 0.0 # Generic notifications play immediately
        }
        self._last_sound_time = {sound_type: 0.0 for sound_type in self.sound_cooldowns}

        # UPDATED: Sound files based on user's provided image and consistent naming
        sound_files = {
            "collision": "./audio/alerts/collision_alert_sound.wav",
            "lane_drift": "./audio/alerts/lane_deviation_sound.wav", 
            "solid_line_crossing": "./audio/alerts/solid_line_sound.wav", 
            "oncoming_traffic_violation": "./audio/alerts/oncoming_alert_sound.wav", 
            "lane_violation_unknown": "./audio/alerts/lane_deviation_sound.wav", # Using lane_deviation_sound for unknown
            "speeding": "./audio/alerts/speed_violation_sound.wav",
            "error": "./audio/alerts/error_encountered_sound.wav",
            "default_notification": "./audio/alerts/alert_sound.wav"
        }

        for sound_type, filename in sound_files.items():
            try:
                if os.path.exists(filename):
                    self.sounds[sound_type] = pygame.mixer.Sound(filename)
                    self.sounds[sound_type].set_volume(0.5) 
                else:
                    print(f"Warning: Sound file '{filename}' for type '{sound_type}' not found. This sound will be disabled.")
                    self.sounds[sound_type] = None
            except pygame.error as e:
                print(f"Warning: Could not load sound '{filename}' for type '{sound_type}': {e}")
                self.sounds[sound_type] = None
        # End Sound Management Modification

        self._persistent_warning = PersistentWarning(self._font_secondary_hud, self.dim, (0,0)) 

        self.help = HelpText(pygame.font.Font(chosen_secondary_font_name, 24), width, height)
        self.server_fps = 0
        self.frame = 0
        self.simulation_time = 0
        self._show_info = True
        self._info_text = []
        self._server_clock = pygame.time.Clock()

        self._active_notifications = [] 
        # MODIFIED: Stacked notifications now start near the bottom and stack upwards
        self._notification_base_pos_y = int(self.dim[1] * 0.85) # Start 85% from top (15% from bottom)
        self._notification_spacing = 8 

        self.current_score = INITIAL_SCORE
        self.total_points_lost_collisions = 0
        self.total_points_lost_lane_violations = 0
        
        self.reset_warning_trackers()

    def _find_font(self, font_names_list, bold=False):
        chosen_font_name = None
        for name in font_names_list:
            matched_font = pygame.font.match_font(name, bold=bold)
            if matched_font:
                chosen_font_name = matched_font
                break
        if not chosen_font_name: 
            if 'mono' in font_names_list or 'courier' in font_names_list : 
                 font_name_os = 'courier' if os.name == 'nt' else 'mono' 
                 fonts = [x for x in pygame.font.get_fonts() if font_name_os in x]
                 default_mono = 'ubuntumono' 
                 mono = default_mono if default_mono in fonts else (fonts[0] if fonts else pygame.font.get_default_font())
                 chosen_font_name = pygame.font.match_font(mono)
            else:
                chosen_font_name = pygame.font.get_default_font() 
        return chosen_font_name


    def reset_warning_trackers(self):
        self._last_collision_count_warned = 0 
        self._last_lane_invasion_count_warned = 0 
        self._last_speed_warning_frame_warned = -1
        self._last_sound_time = {sound_type: 0.0 for sound_type in self.sound_cooldowns}


    def reset(self):
        self.current_score = INITIAL_SCORE
        self.total_points_lost_collisions = 0
        self.total_points_lost_lane_violations = 0
        self.reset_warning_trackers()
        self._active_notifications = [] 

    def on_world_tick(self, timestamp):
        self._server_clock.tick()
        self.server_fps = self._server_clock.get_fps()
        self.frame = timestamp.frame
        self.simulation_time = timestamp.elapsed_seconds

    def play_sound_for_event(self, event_type, force_play=False):
        sound_to_play = self.sounds.get(event_type)
        if not sound_to_play:
            sound_to_play = self.sounds.get("default_notification") 
            if not sound_to_play:
                return 

        current_time = time.time()
        cooldown = self.sound_cooldowns.get(event_type, 0.0) 

        if force_play or current_time > self._last_sound_time.get(event_type, 0.0) + cooldown:
            sound_to_play.play()
            self._last_sound_time[event_type] = current_time


    def deduct_score(self, points, violation_type="unknown"):
        self.current_score -= points
        if self.current_score < 0: self.current_score = 0 
        
        penalty_message = ""
        sound_event_type = violation_type 
        text_color = (255,50,50) # Default penalty color
        symbol_color = (255,100,100) # Default symbol color for penalty

        if violation_type == "collision":
            self.total_points_lost_collisions += points
            penalty_message = f"COLLISION! -{points} PTS"
        elif violation_type == "oncoming_traffic_violation":
            self.total_points_lost_lane_violations += points # Assuming oncoming is a type of lane violation for score tracking
            penalty_message = f"ONCOMING LANE! -{points} PTS"
            text_color = (255, 0, 0) # More severe red
            symbol_color = (255, 0, 0)
        elif violation_type == "solid_line_crossing":
            self.total_points_lost_lane_violations += points
            penalty_message = f"SOLID LINE! -{points} PTS"
            text_color = (255, 100, 0) # Orange for solid line
            symbol_color = (255, 100, 0)
        elif violation_type == "lane_drift":
            self.total_points_lost_lane_violations += points
            penalty_message = f"LANE DRIFT! -{points} PTS"
            text_color = (255, 150, 50) # Lighter orange/yellow
            symbol_color = (255, 150, 50)
        elif violation_type == "lane_violation_unknown":
            self.total_points_lost_lane_violations += points
            penalty_message = f"LANE VIOLATION! -{points} PTS"
            sound_event_type = "lane_drift" # Use drift sound for unknown for now
        else: 
            penalty_message = f"{violation_type.replace('_', ' ').upper()}! -{points} PTS"
            sound_event_type = "default_notification" 

        # Determine if notification should be critical (oncoming is critical)
        is_critical = (violation_type == "oncoming_traffic_violation")

        self.notification(penalty_message, 
                          seconds=3.0 if is_critical else 2.5, 
                          text_color=text_color, 
                          symbol_enabled=True, symbol_color=symbol_color, 
                          is_blinking=is_critical, is_critical_center=is_critical)

        self.play_sound_for_event(sound_event_type, force_play=is_critical)


    def tick(self, world, clock):
        notifications_to_keep = []
        for notif_obj in self._active_notifications:
            notif_obj.tick(world, clock) 
            if notif_obj.seconds_left > 0 or notif_obj.surface.get_alpha() > 0 : 
                notifications_to_keep.append(notif_obj)
        self._active_notifications = notifications_to_keep

        if not self._show_info:
            self._info_text = [] 
            return
        
        if not world.player: 
            self._info_text = [("Player not ready", "secondary")]
            return

        v = world.player.get_velocity()
        c = world.player.get_control()
        
        speed_kmh = 3.6 * math.sqrt(v.x**2 + v.y**2 + v.z**2)

        physics_control = world.player.get_physics_control()
        current_rpm = 0
        if isinstance(c, carla.VehicleControl) and physics_control and hasattr(physics_control, 'max_rpm') and physics_control.max_rpm > 0:
            if c.throttle > 0.01: 
                current_rpm = int(c.throttle * physics_control.max_rpm * 0.8 + 1000) 
            elif speed_kmh > 1.0: 
                current_rpm = int((speed_kmh / 100.0) * (physics_control.max_rpm / 3.0) + 800) 
            else: 
                current_rpm = 800 
            current_rpm = min(current_rpm, int(physics_control.max_rpm))
            current_rpm = max(800, current_rpm) 
        
        gear_display = "N/A"
        if isinstance(c, carla.VehicleControl):
            gear_display = {-1: 'R', 0: 'N'}.get(c.gear, str(c.gear))

        self._info_text = [
            ('SCORE: %d' % self.current_score, 'score_display'), 
            ('', 'spacer_small'), 
            ('SPEED: %3.0f KM/H' % speed_kmh, 'primary'),
            ('RPM: %5.0f' % current_rpm, 'primary'),
            ('GEAR: %s' % gear_display, 'primary'),
            ('', 'spacer_large'), 
        ]

        self._info_text.append(('Collision Penalty: -%d' % self.total_points_lost_collisions, 'penalty_label'))
        self._info_text.append(('Lane Violation Penalty: -%d' % self.total_points_lost_lane_violations, 'penalty_label'))
        
        if speed_kmh > 120: 
            if self.frame > self._last_speed_warning_frame_warned + 180: 
                self.notification("EXCESSIVE SPEED!", 
                                  text_color=(255, 0, 0), seconds=3.0, 
                                  symbol_enabled=True, symbol_color=(255, 0, 0), 
                                  is_blinking=True, is_critical_center=True) 
                self._last_speed_warning_frame_warned = self.frame
                self.play_sound_for_event("speeding") 
        elif self._last_speed_warning_frame_warned != -1: 
            pass 
        

    def toggle_info(self):
        self._show_info = not self._show_info

    def critical_alert(self, text, seconds=2.0, text_color=(255, 255, 255), symbol_color=(255, 255, 0)):
        self.notification(text, seconds=seconds, text_color=text_color, 
                          symbol_enabled=True, symbol_color=symbol_color, 
                          is_blinking=True, is_critical_center=True)
        self.play_sound_for_event("error", force_play=True) 


    def notification(self, text, seconds=2.0, text_color=(255,255,255), 
                     symbol_enabled=False, symbol_color=(255, 0, 0), 
                     is_blinking=False, is_critical_center=False): 
        
        font_size = 48 if is_critical_center else 36 
        symbol_size = 56 if is_critical_center else 42

        # Use custom font if available, otherwise fallback
        if self._use_custom_notification_font:
            notification_text_font = pygame.font.Font(self.custom_notification_font_path, font_size)
            # It's generally safer to use a font known to have symbols for warning icons.
            # If Aeromovedemo.ttf does not contain the '⚠' symbol, it might appear blank or as an unknown character.
            # If you encounter missing symbols, consider changing this line to:
            # notification_symbol_font = pygame.font.Font(pygame.font.get_default_font(), symbol_size)
            notification_symbol_font = pygame.font.Font(self.custom_notification_font_path, symbol_size) 
        else:
            notification_text_font = pygame.font.Font(self._find_font(['ubuntumono', 'arial', 'sans'], bold=True), font_size) 
            notification_symbol_font = pygame.font.Font(pygame.font.get_default_font(), symbol_size) 

        notif_width = self.dim[0] * 0.5 if is_critical_center else 400 
        notif_height = 70 if is_critical_center else 50 

        new_notification = BlinkingAlert(
            font=notification_text_font, 
            symbol_font=notification_symbol_font,
            screen_dim=self.dim, 
            initial_dim=(notif_width, notif_height) 
        )
        new_notification.set_text(text, text_color, seconds, symbol_enabled, symbol_color, is_blinking, is_critical_center)
        
        if not is_critical_center:
            for existing_notif in self._active_notifications:
                # If a non-critical notification with the same text is already active and has time left,
                # just extend its duration instead of adding a new one.
                if not existing_notif.is_critical_center and existing_notif.text == text and existing_notif.seconds_left > 0.5:
                    existing_notif.seconds_left = seconds 
                    return 
        
        self._active_notifications.append(new_notification)
        # Sort so critical alerts are always rendered last (on top)
        self._active_notifications.sort(key=lambda n: not n.is_critical_center)


    def error(self, text):
        self.notification('ERROR: %s' % text.upper(), seconds=5.0, text_color=(255,50,50), 
                          symbol_enabled=True, symbol_color=(255,0,0), 
                          is_blinking=True, is_critical_center=True)
        self.play_sound_for_event("error", force_play=True) 


    def render(self, display):
        if self._show_info and self._info_text:
            hud_panel_width = 350 
            info_surface = pygame.Surface((hud_panel_width, self.dim[1]), pygame.SRCALPHA) 
            info_surface.fill((0, 0, 0, 100)) 
            display.blit(info_surface, (0, 0)) 
            
            v_offset = 10 
            line_padding = 5 

            for item_text, item_type_key in self._info_text:
                if v_offset > self.dim[1] - 20: break 

                font_to_use = self._font_primary_hud
                text_color_to_use = (255, 255, 255) 
                
                if item_type_key == 'secondary':
                    font_to_use = self._font_secondary_hud
                elif item_type_key == 'score_display':
                    font_to_use = self._font_score_hud 
                    text_color_to_use = (255, 255, 0) 
                elif item_type_key == 'penalty_label':
                    font_to_use = self._font_secondary_hud 
                    text_color_to_use = (255, 100, 100) 
                elif item_type_key == 'spacer_small':
                    v_offset += self._font_secondary_hud.get_linesize() // 3
                    continue
                elif item_type_key == 'spacer_large':
                    v_offset += self._font_secondary_hud.get_linesize() // 2
                    continue
                
                text_surface = font_to_use.render(item_text, True, text_color_to_use)
                display.blit(text_surface, (10, v_offset)) 
                v_offset += font_to_use.get_linesize() + line_padding
        
        # MODIFIED START: Reverted notification stacking logic to stack upwards from bottom
        current_stacked_y_offset = self._notification_base_pos_y 
        
        for notif_obj in reversed(self._active_notifications): 
            if notif_obj.surface.get_alpha() == 0 and notif_obj.seconds_left <=0: continue 

            if notif_obj.is_critical_center:
                notif_obj.render(display) 
            else:
                notif_x = (self.dim[0] - notif_obj.surface.get_width()) // 2 
                # Calculate y position for stacking upwards
                notif_y = current_stacked_y_offset - notif_obj.surface.get_height()
                
                # Stop rendering if notifications go too high (e.g., above 15% from top)
                if notif_y < self.dim[1] * 0.15 : break 
                
                display.blit(notif_obj.surface, (notif_x, notif_y))
                # Move the offset upwards for the next notification
                current_stacked_y_offset -= (notif_obj.surface.get_height() + self._notification_spacing)
        # MODIFIED END

        if self.help : self.help.render(display)
        
        if self._persistent_warning: self._persistent_warning.render(display)


# +------------------------------------------------------------------------------+
# | BlinkingAlert Class (MODIFIED from FadingText)                               |
# +------------------------------------------------------------------------------+
class BlinkingAlert(object):
    def __init__(self, font, screen_dim, initial_dim, symbol_font=None):
        self.font = font
        self.screen_dim = screen_dim 
        self.initial_dim = initial_dim 
        
        self.current_pos = [0, 0] 
        self.seconds_left = 0
        
        self.surface = pygame.Surface(self.initial_dim, pygame.SRCALPHA)
        
        self.start_time = 0.0
        self.duration = 0.0
        self.text = "" 
        self.is_blinking = False
        self.is_critical_center = False 

        self.symbol_font = symbol_font if symbol_font else pygame.font.Font(pygame.font.get_default_font(), int(self.initial_dim[1] * 0.7))

        self.bounce_height = 30.0 
        self.bounce_frequency = 2.5 
        self.num_bounces = 2 
        
        self.outline_color = (0, 0, 0) 
        # MODIFIED: Thicker outline
        self.outline_thickness = 3
        self.vertical_bar_width = 12 
        self.vertical_bar_color = (128, 0, 128) 


    def set_text(self, text, text_color=(255, 255, 255), seconds=2.0, 
                 symbol_enabled=True, symbol_color=(255, 255, 0), 
                 is_blinking=False, is_critical_center=False):

        self.text = text
        self.seconds_left = seconds
        self.start_time = pygame.time.get_ticks() / 1000.0
        self.duration = seconds if seconds > 0 else 0.001
        self.is_blinking = is_blinking
        self.is_critical_center = is_critical_center
        self.vertical_bar_color = symbol_color 

        symbol_texture_main = None
        symbol_texture_outline = None
        if symbol_enabled:
            symbol_text_str = "⚠" 
            symbol_texture_main = self.symbol_font.render(symbol_text_str, True, symbol_color)
            symbol_texture_outline = self.symbol_font.render(symbol_text_str, True, self.outline_color)


        display_text_str = text.upper() if self.is_critical_center or self.is_blinking else text
        text_texture_main = self.font.render(display_text_str, True, text_color)
        text_texture_outline = self.font.render(display_text_str, True, self.outline_color)

        padding_horizontal = 20 if self.is_critical_center else 15
        padding_vertical = 15 if self.is_critical_center else 10
        
        content_main_height = max(symbol_texture_main.get_height() if symbol_texture_main else 0, text_texture_main.get_height())
        box_height = content_main_height + 2 * padding_vertical

        content_main_width = text_texture_main.get_width()
        if symbol_texture_main:
            content_main_width += symbol_texture_main.get_width() + (padding_horizontal // 2) 
        
        box_width = content_main_width + padding_horizontal + padding_horizontal + self.vertical_bar_width + (padding_horizontal // 3)
        
        if not self.is_critical_center: 
            box_width = max(box_width, self.initial_dim[0]) 
            box_height = max(box_height, self.initial_dim[1])


        self.surface = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
        
        # --- Draw Gradient Background ---
        base_rgb = (0, 0, 0) 
        gradient_area_width = box_width - self.vertical_bar_width - (padding_horizontal // 3) # Area to the left of the bar
        
        alpha_left = int(255 * 0.1) 
        alpha_right = 220           
        
        for x_col in range(gradient_area_width):
            ratio = x_col / (gradient_area_width -1) if gradient_area_width > 1 else 0
            current_alpha = int(alpha_left + (alpha_right - alpha_left) * ratio)
            current_alpha = max(0, min(255, current_alpha)) 
            line_color = (base_rgb[0], base_rgb[1], base_rgb[2], current_alpha)
            pygame.draw.line(self.surface, line_color, (x_col, 0), (x_col, box_height))

        bar_x = gradient_area_width 
        bar_rect = pygame.Rect(bar_x, 0, self.vertical_bar_width, box_height) 
        pygame.draw.rect(self.surface, self.vertical_bar_color, bar_rect) 

        blit_x_start_content = padding_horizontal 
        current_blit_x_main = blit_x_start_content

        symbol_y_main = (box_height - (symbol_texture_main.get_height() if symbol_texture_main else 0)) // 2
        text_y_main = (box_height - text_texture_main.get_height()) // 2
        
        offsets = []
        for dx_outline in range(-self.outline_thickness, self.outline_thickness + 1):
            for dy_outline in range(-self.outline_thickness, self.outline_thickness + 1):
                if not (dx_outline == 0 and dy_outline == 0): # All points in a square around center
                     offsets.append((dx_outline, dy_outline))
        
        if not offsets and self.outline_thickness > 0: 
             offsets = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]


        temp_blit_x_outline = blit_x_start_content
        if symbol_texture_outline:
            for dx, dy in offsets:
                self.surface.blit(symbol_texture_outline, (temp_blit_x_outline + dx, symbol_y_main + dy))
            temp_blit_x_outline += symbol_texture_outline.get_width() + (padding_horizontal // 2)
            
        for dx, dy in offsets:
             self.surface.blit(text_texture_outline, (temp_blit_x_outline + dx, text_y_main + dy))

        if symbol_texture_main:
            self.surface.blit(symbol_texture_main, (current_blit_x_main, symbol_y_main))
            current_blit_x_main += symbol_texture_main.get_width() + (padding_horizontal // 2)
        
        self.surface.blit(text_texture_main, (current_blit_x_main, text_y_main))

        if self.is_critical_center:
            target_center_y = int(self.screen_dim[1] * 0.40) 
            self.initial_pos = [(self.screen_dim[0] - box_width) // 2, target_center_y - box_height // 2]
        else:
            # For non-critical, notifications start off-screen at the bottom and fade in/move up
            self.initial_pos = [(self.screen_dim[0] - box_width) // 2, self.screen_dim[1]] 
        self.current_pos = list(self.initial_pos)


    def tick(self, _, clock):
        delta_seconds = 1e-3 * clock.get_time()
        self.seconds_left = max(0.0, self.seconds_left - delta_seconds)

        alpha = 0
        if self.seconds_left > 0 and self.duration > 0:
            if self.is_blinking: 
                elapsed_time = (pygame.time.get_ticks() / 1000.0) - self.start_time
                blink_freq = 3.0 if self.is_critical_center else 2.0 
                alpha = int(abs(math.sin(elapsed_time * math.pi * blink_freq)) * 255)
            else: 
                alpha = int(255 * (self.seconds_left / self.duration))
            
            self.surface.set_alpha(max(0, min(255, alpha)))

            if self.is_critical_center and (self.seconds_left > (self.duration - self.num_bounces / self.bounce_frequency)):
                elapsed_bounce_time = (self.duration - self.seconds_left)
                bounce_offset_y = self.bounce_height * (0.5 * (1 - math.cos(elapsed_bounce_time * math.pi * self.bounce_frequency * 2)))
                if elapsed_bounce_time < (1 / (self.bounce_frequency * 2)): 
                     bounce_offset_y = self.bounce_height * math.sin(elapsed_bounce_time * math.pi * self.bounce_frequency * 2)

                self.current_pos[1] = self.initial_pos[1] - bounce_offset_y
            elif self.is_critical_center:
                self.current_pos[1] = self.initial_pos[1] 
        else:
            self.surface.set_alpha(0) 

    def render(self, display):
        if self.is_critical_center and self.surface.get_alpha() > 0:
            display.blit(self.surface, self.current_pos)
            
# +------------------------------------------------------------------------------+
# | HelpText Class                                                               |
# +------------------------------------------------------------------------------+
class HelpText(object):
    def __init__(self, font, width, height):
        lines = __doc__.split('\n') 
        self.font = font 
        line_height = font.get_linesize()
        
        max_line_width = 0
        if lines:
            max_line_width = max(font.size(line)[0] for line in lines)
        
        self.dim = (max_line_width + 44, len(lines) * line_height + 24) 
        
        self.dim = (min(self.dim[0], int(width * 0.8)), min(self.dim[1], int(height * 0.8)))

        self.pos = (0.5 * width - 0.5 * self.dim[0], 0.5 * height - 0.5 * self.dim[1]) 
        
        self.surface = pygame.Surface(self.dim, pygame.SRCALPHA) 
        self.surface.fill((0,0,0,0)) 
        
        bg_color = (0,0,0,200) 
        rect_area = self.surface.get_rect()
        pygame.draw.rect(self.surface, bg_color, rect_area, border_radius=15) 

        current_y = 12 
        for n, line in enumerate(lines):
            if current_y + line_height > self.dim[1] - 12 : break 
            text_texture = self.font.render(line, True, (255, 255, 255)) 
            self.surface.blit(text_texture, (22, current_y)) 
            current_y += line_height
        self._render = False 

    def toggle(self):
        self._render = not self._render

    def render(self, display):
        if self._render:
            display.blit(self.surface, self.pos)

# +------------------------------------------------------------------------------+
# | PersistentWarning Class                                                      |
# +------------------------------------------------------------------------------+
class PersistentWarning(object):
    def __init__(self, font, dim, pos): 
        self.font = font
        self.screen_dim = dim 
        self.text_surface = None 
        self.background_color = (80, 80, 0, 180) 
        self.text_color = (255, 255, 200)   
        self.symbol_color = (255, 255, 0)   
        self.is_active = False

        self.symbol_font = pygame.font.Font(pygame.font.get_default_font(), 22) 

    def set_warning_status(self, text="", active=False):
        self.is_active = active
        if self.is_active:
            symbol_text = "⚠" 
            symbol_texture = self.symbol_font.render(symbol_text, True, self.symbol_color)

            display_text = text.upper() 
            text_texture = self.font.render(display_text, True, self.text_color)

            padding = 8
            content_height = max(symbol_texture.get_height(), text_texture.get_height())
            box_height = content_height + 2 * padding

            content_width = text_texture.get_width() + symbol_texture.get_width() + (padding // 2)
            box_width = content_width + 2 * padding
            
            self.text_surface = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
            pygame.draw.rect(self.text_surface, self.background_color, self.text_surface.get_rect(), border_radius=5)


            current_x_pos = padding
            symbol_y_pos = (box_height - symbol_texture.get_height()) // 2
            text_y_pos = (box_height - text_texture.get_height()) // 2

            self.text_surface.blit(symbol_texture, (current_x_pos, symbol_y_pos))
            current_x_pos += symbol_texture.get_width() + (padding // 2)

            self.text_surface.blit(text_texture, (current_x_pos, text_y_pos))
        else:
            self.text_surface = None 

    def tick(self, world, clock):
        pass

    def render(self, display):
        if self.is_active and self.text_surface:
            render_pos_x = self.screen_dim[0] - self.text_surface.get_width() - 10
            render_pos_y = 10 
            display.blit(self.text_surface, (render_pos_x, render_pos_y))

# +------------------------------------------------------------------------------+
# | CollisionSensor Class                                                        |
# +------------------------------------------------------------------------------+
class CollisionSensor(object):
    def __init__(self, parent_actor, hud):
        self.sensor = None
        self.history = []
        self._parent = parent_actor
        self.hud = hud
        self._last_penalty_time = 0 
        self.total_raw_collisions = 0 

        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.other.collision')
        if bp is None:
            logging.error("Collision sensor blueprint not found!")
            self.hud.error("Collision sensor BP missing")
            return
        try:
            self.sensor = world.spawn_actor(bp, carla.Transform(), attach_to=self._parent)
        except RuntimeError as e:
            logging.error(f"Failed to spawn collision sensor: {e}")
            self.hud.error(f"Spawn collision sensor failed: {e}")
            self.sensor = None 
            return

        if self.sensor is None: 
            logging.error("Collision sensor is None after spawn attempt.")
            self.hud.error("Collision sensor None post-spawn")
            return
        
        weak_self = weakref.ref(self)
        self.sensor.listen(lambda event: CollisionSensor._on_collision(weak_self, event))

    def get_col_count(self): 
        return self.total_raw_collisions 
    
    @staticmethod
    def _on_collision(weak_self, event):
        self = weak_self()
        if not self or not self.hud : return 

        self.total_raw_collisions += 1 

        current_time = time.time() 
        if current_time > self._last_penalty_time + COLLISION_COOLDOWN_SECONDS:
            self.hud.deduct_score(COLLISION_PENALTY, "collision")
            self._last_penalty_time = current_time
        
        impulse = event.normal_impulse
        intensity = math.sqrt(impulse.x**2 + impulse.y**2 + impulse.z**2)
        self.history.append((event.frame, intensity))
        if len(self.history) > 4000: self.history.pop(0) 


# +------------------------------------------------------------------------------+
# | LaneInvasionSensor Class                                                     |
# +------------------------------------------------------------------------------+
class LaneInvasionSensor(object):
    def __init__(self, parent_actor, hud):
        self.sensor = None
        self._parent = parent_actor
        self.hud = hud
        self.total_raw_invasions = 0 
        self._last_penalty_frame = -1 # Frame-based cooldown for penalties

        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.other.lane_invasion')
        if bp is None: 
            logging.error("Lane invasion sensor blueprint not found!")
            self.hud.error("Lane invasion sensor BP missing")
            return
        
        try:
            self.sensor = world.spawn_actor(bp, carla.Transform(), attach_to=self._parent)
        except RuntimeError as e:
            logging.error(f"Failed to spawn lane invasion sensor: {e}")
            self.hud.error(f"Spawn lane invasion sensor failed: {e}")
            self.sensor = None
            return

        if self.sensor is None:
            logging.error("Lane invasion sensor is None after spawn attempt.")
            self.hud.error("Lane invasion sensor None post-spawn")
            return

        weak_self = weakref.ref(self) 
        self.sensor.listen(lambda event: LaneInvasionSensor._on_invasion(weak_self, event))

    def get_invasion_count(self): 
        return self.total_raw_invasions
    
    @staticmethod
    def _on_invasion(weak_self, event):
        self = weak_self()
        if not self or not self.hud: return

        self.total_raw_invasions += 1 

        player = self._parent
        world = player.get_world()
        carla_map = world.get_map()
        player_transform = player.get_transform()
        player_location = player_transform.location
        player_forward_vec = player_transform.get_forward_vector()

        # Waypoint for the lane the player is currently occupying *after* the invasion
        occupied_waypoint = carla_map.get_waypoint(player_location, project_to_road=True, lane_type=carla.LaneType.Driving)

        if not occupied_waypoint:
            # If no occupied waypoint is found, it's an unknown lane violation
            current_frame = self.hud.frame
            if current_frame > self._last_penalty_frame + 30:
                self.hud.deduct_score(LANE_VIOLATION_PENALTY, "lane_violation_unknown")
                self._last_penalty_frame = current_frame
            return

        occupied_lane_forward_vec = occupied_waypoint.transform.get_forward_vector()
        
        # Use 2D vectors for directional comparison on the XY plane
        player_forward_vec_2d = carla.Vector2D(player_forward_vec.x, player_forward_vec.y)
        if player_forward_vec_2d.length()**2 > 0: # Avoid division by zero if vector is (0,0)
            player_forward_vec_2d = player_forward_vec_2d.make_unit_vector()

        occupied_lane_forward_vec_2d = carla.Vector2D(occupied_lane_forward_vec.x, occupied_lane_forward_vec.y)
        if occupied_lane_forward_vec_2d.length()**2 > 0:
            occupied_lane_forward_vec_2d = occupied_lane_forward_vec_2d.make_unit_vector()

        # Calculate dot product to determine if player is going against the lane direction
        dot_product_with_occupied_lane = player_forward_vec_2d.x * occupied_lane_forward_vec_2d.x + \
                                         player_forward_vec_2d.y * occupied_lane_forward_vec_2d.y

        is_oncoming_violation = False
        is_solid_line_violation = False
        violation_type_for_penalty = "lane_drift" # Default to least severe if specific conditions not met

        # If dot product is significantly negative, it indicates oncoming traffic
        if dot_product_with_occupied_lane < -0.7: # Threshold for "oncoming"
            is_oncoming_violation = True
            violation_type_for_penalty = "oncoming_traffic_violation"
        else:
            # Check for solid line crossings if not an oncoming violation
            for marking in event.crossed_lane_markings:
                # Use only commonly available LaneMarkingType attributes
                # Based on CARLA 0.9.15 documentation, the most reliable are Solid and Broken.
                # DoubleSolidYellow, SolidYellow, SolidWhite, DoubleSolid are not consistently present.
                if marking.type in [carla.LaneMarkingType.Solid, carla.LaneMarkingType.SolidSolid]:
                    is_solid_line_violation = True
                    violation_type_for_penalty = "solid_line_crossing"
                    break 
        
        current_frame = self.hud.frame
        # Apply penalty with a cooldown
        if current_frame > self._last_penalty_frame + 30:  # 30 frames cooldown
            actual_penalty_amount = LANE_VIOLATION_PENALTY # Base penalty
            if is_oncoming_violation:
                actual_penalty_amount = int(LANE_VIOLATION_PENALTY * ONCOMING_TRAFFIC_PENALTY_MULTIPLIER)
            elif is_solid_line_violation:
                actual_penalty_amount = int(LANE_VIOLATION_PENALTY * SOLID_LINE_CROSSING_PENALTY_MULTIPLIER)
            
            self.hud.deduct_score(actual_penalty_amount, violation_type_for_penalty)
            self._last_penalty_frame = current_frame

# +------------------------------------------------------------------------------+
# | GnssSensor Class                                                             |
# +------------------------------------------------------------------------------+
class GnssSensor(object):
    def __init__(self, parent_actor):
        self.sensor = None
        self._parent = parent_actor
        self.lat, self.lon = 0.0, 0.0
        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.other.gnss')
        if bp is None:
            logging.error("GNSS sensor blueprint not found!")
            return
        try:
            self.sensor = world.spawn_actor(bp, carla.Transform(carla.Location(x=1.0, z=2.8)), attach_to=self._parent)
        except RuntimeError as e:
            logging.error(f"Failed to spawn GNSS sensor: {e}")
            self.sensor = None
            return
        
        if self.sensor is None:
            logging.error("GNSS sensor is None after spawn attempt.")
            return

        weak_self = weakref.ref(self)
        self.sensor.listen(lambda event: GnssSensor._on_gnss_event(weak_self, event))

    @staticmethod
    def _on_gnss_event(weak_self, event):
        self = weak_self()
        if not self: return
        self.lat, self.lon = event.latitude, event.longitude

# +------------------------------------------------------------------------------+
# | CameraManager Class                                                          |
# +------------------------------------------------------------------------------+
class CameraManager(object):
    def __init__(self, parent_actor, hud, fov=90.0): 
        self.sensor = None
        self.surface = None
        self._parent = parent_actor
        self.hud = hud
        self.fov = fov 
        self.recording = False
        self._camera_transforms = [
            carla.Transform(carla.Location(x=-10, z=7), carla.Rotation(pitch=-20)), 
            carla.Transform(carla.Location(x=1.05,y=-0.4, z=1.6), carla.Rotation(pitch=0)) 
        ]
        self.transform_index = 1 
        self.sensors = [
            ['sensor.camera.rgb', cc.Raw, 'Camera RGB'],
            ['sensor.camera.depth', cc.Raw, 'Camera Depth (Raw)'],
            ['sensor.camera.depth', cc.Depth, 'Camera Depth (Gray Scale)'],
            ['sensor.camera.depth', cc.LogarithmicDepth, 'Camera Depth (Logarithmic Gray Scale)'],
            ['sensor.camera.semantic_segmentation', cc.Raw, 'Camera Semantic Segmentation (Raw)'],
            ['sensor.camera.semantic_segmentation', cc.CityScapesPalette, 'Camera Semantic Segmentation (CityScapes Palette)'],
            ['sensor.lidar.ray_cast', None, 'Lidar (Ray-Cast)']
        ]
        world = self._parent.get_world()
        bp_library = world.get_blueprint_library()
        for item in self.sensors:
            bp = bp_library.find(item[0])
            if bp is None:
                logging.warning(f"CameraManager: Blueprint for sensor {item[0]} not found. Skipping.")
                item.append(None) 
                continue

            if item[0].startswith('sensor.camera'):
                bp.set_attribute('image_size_x', str(hud.dim[0]))
                bp.set_attribute('image_size_y', str(hud.dim[1]))
                if bp.has_attribute('fov'):
                    if item[0] == 'sensor.camera.rgb':
                         bp.set_attribute('fov', str(self.fov)) 
                    else: 
                        bp.set_attribute('fov', '90') 
            elif item[0].startswith('sensor.lidar'):
                if bp.has_attribute('range'): bp.set_attribute('range', '50')
            item.append(bp)
        self.index = None 

    def toggle_camera(self):
        self.transform_index = (self.transform_index + 1) % len(self._camera_transforms)
        if self.sensor: 
            try:
                self.sensor.set_transform(self._camera_transforms[self.transform_index])
            except RuntimeError as e:
                logging.error(f"Error setting camera transform: {e}")
                self.hud.error(f"Cam transform error: {e}")


    def set_sensor(self, index, notify=True):
        index = index % len(self.sensors)
        
        if self.sensors[index][-1] is None:
            logging.warning(f"Cannot set sensor: Blueprint for {item[0]} not found. Skipping.")
            if notify: self.hud.error(f"Sensor {self.sensors[index][2]} unavailable (BP missing)")
            return

        needs_respawn = True 
        if self.index is not None and self.sensors[index][0] == self.sensors[self.index][0]:
            needs_respawn = False 
            needs_respawn = True 


        if needs_respawn:
            if self.sensor is not None:
                self.sensor.destroy()
                self.surface = None
            try:
                self.sensor = self._parent.get_world().spawn_actor(
                    self.sensors[index][-1], 
                    self._camera_transforms[self.transform_index], 
                    attach_to=self._parent)
            except RuntimeError as e:
                logging.error(f"Error spawning sensor {self.sensors[index][0]}: {e}")
                self.hud.error(f"Spawn {self.sensors[index][2]} failed: {e}")
                self.sensor = None
                self.index = None
                return

            if self.sensor is None: 
                logging.error(f"Sensor {self.sensors[index][0]} is None after spawn attempt.")
                self.hud.error(f"{self.sensors[index][2]} None post-spawn")
                self.index = None
                return

            weak_self = weakref.ref(self)
            self.sensor.listen(lambda image: CameraManager._parse_image(weak_self, image))
        
        if notify: self.hud.notification(self.sensors[index][2]) 
        self.index = index


    def next_sensor(self):
        current_index = self.index if self.index is not None else -1
        self.set_sensor(current_index + 1)

    def toggle_recording(self):
        self.recording = not self.recording
        self.hud.notification('Recording %s' % ('On' if self.recording else 'Off'))
        if self.recording:
            try:
                if not os.path.exists('_out'): 
                    os.makedirs('_out')
            except OSError as e:
                logging.error(f"Error creating output directory '_out': {e}")
                self.hud.error(f"Record dir error: {e}")
                self.recording = False 


    def render(self, display):
        if self.surface is not None: 
            display.blit(self.surface, (0, 0))

    @staticmethod
    def _parse_image(weak_self, image):
        self = weak_self()
        if not self or self.index is None or self.sensors[self.index][-1] is None: 
            return
        
        sensor_type = self.sensors[self.index][0]
        color_converter = self.sensors[self.index][1]

        if sensor_type.startswith('sensor.lidar'):
            points = np.frombuffer(image.raw_data, dtype=np.dtype('f4'))
            points = np.reshape(points, (int(points.shape[0] / 4), 4)) 
            lidar_data = np.array(points[:, :2]) 
            
            lidar_data *= min(self.hud.dim) / (2 * 50.0) 
            lidar_data[:,0] += self.hud.dim[0] / 2.0 
            lidar_data[:,1] += self.hud.dim[1] / 2.0 
            
            lidar_data = np.fabs(lidar_data) 
            lidar_data = lidar_data.astype(np.int32)
            
            valid_points_mask = (lidar_data[:, 0] < self.hud.dim[0]) & (lidar_data[:, 0] >= 0) & \
                                (lidar_data[:, 1] < self.hud.dim[1]) & (lidar_data[:, 1] >= 0)
            lidar_data = lidar_data[valid_points_mask]
            
            lidar_img_size = (self.hud.dim[0], self.hud.dim[1], 3)
            lidar_img = np.zeros(lidar_img_size, dtype=np.uint8)
            
            if lidar_data.shape[0] > 0:
                 lidar_img[lidar_data[:, 1], lidar_data[:, 0]] = (255, 255, 255) 
            
            self.surface = pygame.surfarray.make_surface(lidar_img.swapaxes(0,1)) 
        
        elif sensor_type.startswith('sensor.camera'):
            if color_converter is not None: 
                image.convert(color_converter)
            
            array = np.frombuffer(image.raw_data, dtype=np.dtype("uint8"))
            array = np.reshape(array, (image.height, image.width, 4)) 
            array = array[:, :, :3] 
            array = array[:, :, ::-1] 
            self.surface = pygame.surfarray.make_surface(array.swapaxes(0, 1)) 
        
        if self.recording and hasattr(image, 'save_to_disk'): 
            try:
                image.save_to_disk('_out/%08d' % image.frame)
            except Exception as e: 
                logging.error(f"Error saving image to disk: {e}")
                self.recording = False 

# +------------------------------------------------------------------------------+
# | Game Loop Function                                                           |
# +------------------------------------------------------------------------------+
def game_loop(args):
    pygame.init()
    pygame.font.init()
    world = None 
    hud = None 
    try:
        client = carla.Client(args.host, args.port)
        client.set_timeout(300.0) 

        display_info = pygame.display.Info()
        native_width = display_info.current_w
        native_height = display_info.current_h

        display_flags = pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.FULLSCREEN 
        
        display = pygame.display.set_mode(
            (native_width, native_height), 
            display_flags)

        pygame.display.set_caption("CARLA Fanatec Simulation") 
        print(f"Pygame Display Mode Set: Native Fullscreen: {native_width}x{native_height}")

        hud = HUD(native_width, native_height, args) # Pass args to HUD
        world = World(client.get_world(), hud, args.filter, args.fov) 
        controller = DualControl(world, args.autopilot) 

        clock = pygame.time.Clock()
        while True:
            clock.tick_busy_loop(60) 
            if controller.parse_events(world, clock): 
                return
            
            if world: world.tick(clock) 
            if world: world.render(display) 
            
            pygame.display.flip() 

    except Exception as e: 
        logging.error(f"Critical error in game loop: {e}", exc_info=True)
        if hud: hud.error(f"GAME LOOP CRASH: {type(e).__name__}") 
        if 'display' in locals() and display and hud: 
            pygame.display.flip() 
            time.sleep(5) 
    finally:
        if world is not None: 
            logging.info("Destroying world...")
            world.destroy()
            logging.info("World destroyed.")
        pygame.quit()
        logging.info("Pygame quit.")

# ==============================================================================
# -- main() -- function --------------------------------------------------------
# ==============================================================================
def main():
    argparser = argparse.ArgumentParser(description='CARLA Manual Control Client')
    argparser.add_argument('-v', '--verbose', action='store_true', dest='debug', help='print debug information')
    argparser.add_argument('--host', metavar='H', default='localhost', help='IP of the host server (default: 127.0.0.1)')
    argparser.add_argument('-p', '--port', metavar='P', default=2000, type=int, help='TCP port to listen to (default: 2000)')
    argparser.add_argument('-a', '--autopilot', action='store_true', help='enable autopilot')
    argparser.add_argument(
        '--res',
        metavar='WIDTHxHEIGHT',
        default='1280x720', 
        help='Internal rendering resolution for cameras if not fullscreen (e.g., 1280x720). Fullscreen uses native.')
    argparser.add_argument('--filter', metavar='PATTERN', default='vehicle.*', help='actor filter (default: "vehicle.*")')
    argparser.add_argument(
        '--carla-root',
        metavar='PATH',
        default=os.environ.get('CARLA_ROOT', ''), 
        help='Path to CARLA installation directory (e.g., /opt/carla-simulator/ or C:\\carla)')
    argparser.add_argument(
        '--no-launch-carla',
        action='store_true',
        help='Do not launch CARLA server, assume it is already running.')
    argparser.add_argument(
        '--fov',
        metavar='FOV',
        default=120.0, # MODIFIED: Default FOV to 120
        type=float,
        help='Horizontal field of view for the RGB camera (default: 120.0 degrees)')
    args = argparser.parse_args()

    try:
        args.width, args.height = [int(x) for x in args.res.split('x')]
    except ValueError:
        logging.error("Invalid resolution format for --res. Expected WIDTHxHEIGHT (e.g., 1280x720). Using default.")
        args.width, args.height = 1280, 720 


    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format='%(levelname)s: %(message)s', level=log_level)
    logging.info('listening to server %s:%s', args.host, args.port)
    print(__doc__) 

    global carla_server_process

    try:
        if not args.no_launch_carla:
            if not args.carla_root:
                logging.error("CARLA_ROOT path is not provided via --carla-root argument or CARLA_ROOT environment variable.")
                logging.error("Please specify the path to your CARLA installation.")
                sys.exit(1)

            common_carla_args = [
                f'-carla-rpc-port={args.port}',
                '-quality-level=Epic',
                '-RenderOffScreen'  
            ]

            if sys.platform == 'win32':
                carla_server_executable_packaged = os.path.join(args.carla_root, 'WindowsNoEditor', 'CarlaUE4.exe')
                carla_server_executable_dev = os.path.join(args.carla_root, 'CarlaUE4', 'Binaries', 'Win64', 'CarlaUE4.exe')

                if os.path.exists(carla_server_executable_packaged):
                    carla_server_executable = carla_server_executable_packaged
                elif os.path.exists(carla_server_executable_dev):
                    carla_server_executable = carla_server_executable_dev
                else:
                    logging.error(f"CARLA server executable not found in common locations within: {args.carla_root}")
                    logging.error("Checked: " + carla_server_executable_packaged)
                    logging.error("Checked: " + carla_server_executable_dev)
                    sys.exit(1)
                
                command = [carla_server_executable] + common_carla_args
            
            elif sys.platform.startswith('linux'):
                carla_server_executable = os.path.join(args.carla_root, 'CarlaUE4.sh')
                command = [carla_server_executable] + common_carla_args
            else:
                logging.error(f"Unsupported OS for launching CARLA server: {sys.platform}")
                sys.exit(1)

            if not os.path.exists(carla_server_executable): 
                logging.error(f"CARLA server executable not found at determined path: {carla_server_executable}")
                sys.exit(1)

            logging.info(f"Launching CARLA server: {' '.join(command)}")
            carla_server_process = subprocess.Popen(command)

            logging.info("Waiting for CARLA server to start (approx. 10-30 seconds)...")
            time.sleep(15) 
            
        game_loop(args)

    except KeyboardInterrupt: 
        print('\nCancelled by user. Exiting...')
    except Exception as e: 
        logging.critical(f"Unhandled exception in main execution: {e}", exc_info=True)
    finally:
        if carla_server_process is not None and carla_server_process.poll() is None: 
            logging.info("Terminating CARLA server process...")
            carla_server_process.terminate() 
            try:
                carla_server_process.wait(timeout=10) 
                logging.info("CARLA server process terminated gracefully.")
            except subprocess.TimeoutExpired:
                logging.warning("CARLA server did not terminate gracefully after 10s, forcing kill.")
                carla_server_process.kill() 
                logging.info("CARLA server process killed.")
        elif carla_server_process is not None:
             logging.info("CARLA server process already terminated.")
        
        pygame.quit() 
        print("Script finished.")


if __name__ == '__main__':
    main()

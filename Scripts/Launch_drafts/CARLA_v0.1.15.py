"""
Subject: CARLA, Fanatec-CSL~series Integration
Author: CARLA-dev, Arjun Joshi
Recent Date: 05.15.2025
Versioning: v0.1.2
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

# Import Packages, Locate CARLA packages
from __future__ import print_function
import glob
import os
import sys
import subprocess # ADDED: For launching CARLA server
import time       # ADDED: For delays

# try: # Original CARLA path appending - typically handled by CARLA_PATH environment variable
#     sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg')
#         sys.version_info.major,
#         sys.version_info.minor,
#         'win-amd64' if os.name == 'nt' else 'linux-x86_64')[0]
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
    def __init__(self, carla_world, hud, actor_filter):
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
        self.restart()
        self.world.on_tick(hud.on_world_tick)

    def restart(self):
        # Keep same camera config if the camera manager exists.
        cam_index = self.camera_manager.index if self.camera_manager is not None else 0
        cam_pos_index = self.camera_manager.transform_index if self.camera_manager is not None else 0
        # Get a random blueprint.
        blueprint = random.choice(self.world.get_blueprint_library().filter(self._actor_filter))
        blueprint.set_attribute('role_name', 'hero') # Keep the 'hero' role name convention
        if blueprint.has_attribute('color'):
            color = random.choice(blueprint.get_attribute('color').recommended_values)
            blueprint.set_attribute('color', color)
        # Spawn the player.
        if self.player is not None:
            spawn_point = self.player.get_transform()
            spawn_point.location.z += 2.0
            spawn_point.rotation.roll = 0.0
            spawn_point.rotation.pitch = 0.0
            self.destroy()
            self.player = self.world.try_spawn_actor(blueprint, spawn_point)
        while self.player is None:
            spawn_points = self.world.get_map().get_spawn_points()
            spawn_point = random.choice(spawn_points) if spawn_points else carla.Transform()
            self.player = self.world.try_spawn_actor(blueprint, spawn_point)

        # Ensure autopilot is off for manual control
        if isinstance(self.player, carla.Vehicle):
            self.player.set_autopilot(False)

        # Set up the sensors.
        # MODIFIED: Pass self.hud.critical_alert and self.hud.notification methods to sensors if they use them directly
        self.collision_sensor = CollisionSensor(self.player, self.hud)
        self.lane_invasion_sensor = LaneInvasionSensor(self.player, self.hud)
        self.gnss_sensor = GnssSensor(self.player)
        self.camera_manager = CameraManager(self.player, self.hud)
        self.camera_manager.transform_index = cam_pos_index
        self.camera_manager.set_sensor(cam_index, notify=False)
        actor_type = get_actor_display_name(self.player)
        self.hud.notification(actor_type, seconds = 2.0) #Informational : actor type spawned

    def next_weather(self, reverse=False):
        self._weather_index += -1 if reverse else 1
        self._weather_index %= len(self._weather_presets)
        preset = self._weather_presets[self._weather_index]
        self.hud.notification('Weather: %s' % preset[1])
        self.player.get_world().set_weather(preset[0])

    def tick(self, clock):
        self.hud.tick(self, clock)
        # Update spectator view to driver's seat
        if self.player is not None and isinstance(self.player, carla.Vehicle):
            spectator = self.world.get_spectator()
            vehicle_transform = self.player.get_transform()
            
            driver_seat_offset_location = carla.Location(x=0.8, y=0.0, z=1.6)
            rotated_offset = vehicle_transform.transform_vector(driver_seat_offset_location)
            spectator_location = vehicle_transform.location + rotated_offset
            spectator_transform = carla.Transform(spectator_location, vehicle_transform.rotation)
            # Removed print statement for debug
            # print(f"Vehicle Transform Rotation:, {vehicle_transform.rotation}, Vehicle Transform Location Debug info:, {vehicle_transform.location}, Spectator Offset Location {spectator_transform.location}") 
            spectator.set_transform(spectator_transform)

    def render(self, display):
        self.camera_manager.render(display)
        self.hud.render(display)

    def destroy(self):
        sensors = [
            self.camera_manager.sensor,
            self.collision_sensor.sensor,
            self.lane_invasion_sensor.sensor,
            self.gnss_sensor.sensor]
        for sensor in sensors:
            if sensor is not None:
                sensor.stop()
                sensor.destroy()
        if self.player is not None:
            self.player.destroy()


# +------------------------------------------------------------------------------+
# | DualControl Class                                                            |
# +------------------------------------------------------------------------------+

class DualControl(object):
    def __init__(self, world, start_in_autopilot):
        self._autopilot_enabled = start_in_autopilot
        if isinstance(world.player, carla.Vehicle):
            self._control = carla.VehicleControl()
            # Ensure autopilot is off for manual control
            world.player.set_autopilot(False)
        elif isinstance(world.player, carla.Walker):
            self._control = carla.WalkerControl()
            self._autopilot_enabled = False
            self._rotation = world.player.get_transform().rotation
        else:
            raise NotImplementedError("Actor type not supported")
        self._steer_cache = 0.0 # Kept from original for potential smoothing if needed

        world.hud.notification("Press 'H' or '?' for help.", seconds=4.0)

        # --- Fanatec Hardware Initialization and Configuration ---
        pygame.joystick.init()

        joystick_count = pygame.joystick.get_count()
        if joystick_count == 0:
            raise ValueError("No joysticks found. Please connect your Fanatec wheel kit.")

        print(f"Found {joystick_count} joystick(s).")

        # --- IMPORTANT: Configure these indices for EACH HARDWARE CONFIGURATION, SPECIFIC FANATEC SETUP & (potentially) INSTANCE ---
        # Use the output from the joystick_input_finder.py script to find these values.

        # Joystick index for the steering wheel (often 0 or 1)
        self._steer_joystick_idx = 1 # * REPLACE WITH YOUR STEERING JOYSTICK INDEX

        # Joystick index for the pedals (often 0 or 1, might be same as wheel)
        self._pedal_joystick_idx = 1 # * REPLACE WITH PEDAL JOYSTICK INDEX

        # Axis index for steering rotation (-1.0 to 1.0)
        self._steer_axis_idx = 0 # * REPLACE WITH STEERING AXIS INDEX

        # Axis index for throttle pedal (check its range, e.g., -1.0 to 1.0 or 0.0 to 1.0)
        self._throttle_axis_idx = 1 # * REPLACE WITH THROTTLE AXIS INDEX

        # Axis index for brake pedal (check its range)
        self._brake_axis_idx = 5 # * REPLACE WITH BRAKE AXIS INDEX

        # Example Button indices (replace with actual button indices)
        self._handbrake_button_idx = 11 # REPLACE WITH HANDBRAKE BUTTON INDEX (if button)
        self._reverse_button_idx = 26   # * REPLACE WITH REVERSE BUTTON INDEX (if button)
        self._gear_up_button_idx = 3   # * REPLACE WITH GEAR UP BUTTON INDEX (if button)
        self._gear_down_button_idx = 0 # * REPLACE WITH GEAR DOWN BUTTON INDEX (if button)
        self._gear_mode_manual = 7 # * REPLACE WITH MANUAL GEAR SHIFT BUTTON INDEX (if button)


        # Get references to the specific joystick objects
        try:
            self._steer_joystick = pygame.joystick.Joystick(self._steer_joystick_idx)
            self._steer_joystick.init()
            print(f"Steering Joystick {self._steer_joystick_idx}: {self._steer_joystick.get_name()}")

            # Check if pedal joystick is different, initialize if necessary
            if self._pedal_joystick_idx != self._steer_joystick_idx:
                self._pedal_joystick = pygame.joystick.Joystick(self._pedal_joystick_idx)
                self._pedal_joystick.init()
                print(f"Pedal Joystick {self._pedal_joystick_idx}: {self._pedal_joystick.get_name()}")
            else:
                self._pedal_joystick = self._steer_joystick # Use the same object if indices are the same

        except pygame.error as e:
            raise ValueError(f"Error initializing joystick: {e}")


        # --- Input Mapping Parameters (Adjust these for feel and deadzones) ---
        self._steer_deadzone = 0.05  # Deadzone for steering near center
        self._pedal_deadzone = 0.02  # Deadzone for pedals near released position

        # Optional: Steering linearity factor (1.0 is linear, <1.0 makes center less sensitive)
        self._steer_linearity = 1.0


    def parse_events(self, world, clock):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            # --- Keep original keyboard controls for HUD, camera, weather etc. ---
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
                    world.camera_manager.toggle_camera()
                elif event.key == K_c and pygame.key.get_mods() & KMOD_SHIFT:
                    world.next_weather(reverse=True)
                elif event.key == K_c:
                    world.next_weather()
                elif event.key == K_BACKQUOTE:
                    world.camera_manager.next_sensor()
                elif event.key > K_0 and event.key <= K_9:
                    world.camera_manager.set_sensor(event.key - 1 - K_0)
                elif event.key == K_r:
                    world.camera_manager.toggle_recording()
                if isinstance(self._control, carla.VehicleControl):
                    # Keep keyboard gear shift and autopilot toggles
                    if event.key == K_q:
                        self._control.gear = 1 if self._control.reverse else -1
                    elif event.key == K_m:
                        self._control.manual_gear_shift = not self._control.manual_gear_shift
                        self._control.gear = world.player.get_control().gear
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

            # --- Handle Joystick Button Events ---
            elif event.type == pygame.JOYBUTTONDOWN:
                # Keep original button mappings (like restart, HUD, camera) if they align
                # Otherwise, map them to Fanatec buttons or remove
                if event.button == 8 and event.joy == self._steer_joystick_idx: # Example: Button 0 on steer joystick restarts
                    world.restart()
                # Add mappings for other common actions if needed
                # elif event.button == 1 and event.joy == self._steer_joystick_idx: # Example: Button 1 toggles info
                #     world.hud.toggle_info()

                # --- Handle Fanatec Specific Button Mappings ---
                if isinstance(self._control, carla.VehicleControl):
                    # Handbrake button (toggle state)
                    if event.joy == self._steer_joystick_idx and event.button == self._handbrake_button_idx:
                        self._control.hand_brake = not self._control.hand_brake
                        world.hud.notification('Handbrake %s' % ('On' if self._control.hand_brake else 'Off'))

                    # MODIFIED: More robust reverse gear toggle logic
                    if event.joy == self._steer_joystick_idx and event.button == self._reverse_button_idx:
                        # Toggle between Reverse (-1) and Drive (1) or Neutral (0)
                        if self._control.gear == -1: # If currently in reverse, switch to 1st gear (or neutral if stopped)
                            self._control.gear = 1 if world.player.get_velocity().length() > 0.1 else 0 # Go to 1st if moving, else Neutral
                            self._control.reverse = False
                            world.hud.notification('Gear: D' if self._control.gear == 1 else 'Gear: N')
                        else: # If not in reverse, switch to reverse
                            self._control.gear = -1
                            self._control.reverse = True
                            world.hud.notification('Gear: R')

                    # Manual Gear Shift (Toggle manual mode)
                    if event.joy == self._steer_joystick_idx and event.button == self._gear_mode_manual:
                        self._control.manual_gear_shift = not self._control.manual_gear_shift
                        self._control.gear = world.player.get_control().gear # Sync gear display
                        world.hud.notification('%s Transmission' % ('Manual' if self._control.manual_gear_shift else 'Automatic'))

                    # Gear Up (if in manual mode)
                    if self._control.manual_gear_shift and event.joy == self._steer_joystick_idx and event.button == self._gear_up_button_idx:
                        self._control.gear = self._control.gear + 1
                        world.hud.notification('Gear: %s' % self._control.gear)

                    # Gear Down (if in manual mode)
                    if self._control.manual_gear_shift and event.joy == self._steer_joystick_idx and event.button == self._gear_down_button_idx:
                        self._control.gear = max(-1, self._control.gear - 1)
                        world.hud.notification('Gear: %s' % {-1: 'R', 0: 'N'}.get(self._control.gear, self._control.gear))


            # --- Handle Joystick Hat (D-pad) Events ---
            elif event.type == pygame.JOYHATMOTION:
                # Example: Map D-pad to camera views or menu navigation
                # if event.joy == YOUR_HAT_JOYSTICK_INDEX and event.hat == YOUR_HAT_INDEX:
                #     hat_direction = event.value # Tuple like (0, 1) for Up
                #     if hat_direction == (0, 1):
                #          world.camera_manager.next_sensor() # Example: Up on D-pad changes camera sensor
                #     elif hat_direction == (0, -1):
                #          world.camera_manager.toggle_camera() # Example: Down on D-pad toggles camera view
                pass


        # --- Apply Control Based on Current Input State ---
        # This happens every tick, regardless of whether an event occurred
        if not self._autopilot_enabled:
            if isinstance(self._control, carla.VehicleControl):
                # Removed _parse_vehicle_keys as we only use wheel input now
                self._parse_vehicle_wheel() # Read and map wheel/pedal inputs
                # _control.reverse and _control.hand_brake are handled by button events
                # _control.manual_gear_shift and _control.gear are handled by button/key events
            elif isinstance(self._control, carla.WalkerControl):
                self._parse_walker_keys(pygame.key.get_pressed(), clock.get_time()) # Keep walker controls if needed

            # Apply the control to the vehicle
            # Note: Original script uses world.player.apply_control(self._control) inside this if block
            # Make sure this line is present and correctly indented in the final script
            world.player.apply_control(self._control)

    def _parse_vehicle_wheel(self):
        # --- Read Raw Fanatec Axis Inputs ---
        # Get raw values from the configured joystick axes
        try:
            raw_steer = self._steer_joystick.get_axis(self._steer_axis_idx)
            raw_throttle = self._pedal_joystick.get_axis(self._throttle_axis_idx)
            raw_brake = self._pedal_joystick.get_axis(self._brake_axis_idx)
        except pygame.error as e:
            print(f"Error reading joystick axis: {e}")
            # Handle error - maybe set control values to zero or previous state
            raw_steer = 0.0
            raw_throttle = -1.0 # Default raw pedal value when released
            raw_brake = -1.0    # Default raw pedal value when released


        # --- Map Raw Inputs to CARLA's Expected Range (0.0 to 1.0 or -1.0 to 1.0) ---
        # These mapping functions need to be adjusted based on your hardware's output range and feel.

        # Steering: Raw value is usually -1.0 (left) to 1.0 (right)
        # Apply deadzone and optional linearity
        steer_cmd = raw_steer
        if abs(steer_cmd) < self._steer_deadzone:
            steer_cmd = 0.0
        # Optional: Apply linearity (adjust self._steer_linearity)
        # steer_cmd = math.copysign(steer_cmd**self._steer_linearity, steer_cmd)


        # Throttle and Brake: Raw value is often -1.0 (released) to 1.0 (pressed) for pedals
        # Map to 0.0 (released) to 1.0 (pressed)
        throttle_cmd = (1.0 - raw_throttle) / 2.0 # Maps -1 to 0, 1 to 1
        brake_cmd = (1.0 - raw_brake) / 2.0       # Maps -1 to 0, 1 to 1

        # Apply pedal deadzone (at the released end)
        if throttle_cmd < self._pedal_deadzone:
            throttle_cmd = 0.0
        if brake_cmd < self._pedal_deadzone:
            brake_cmd = 0.0

        # --- Assign Mapped Values to CARLA Control Object ---
        self._control.steer = steer_cmd
        self._control.brake = brake_cmd
        self._control.throttle = throttle_cmd

        # Handbrake is handled by button events in parse_events

    # Kept _parse_walker_keys as it's part of the original framework for walker control

    def _parse_walker_keys(self, keys, milliseconds):
        self._control.speed = 0.0
        if keys[K_DOWN] or keys[K_s]:
            self._control.speed = 0.0
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
    def __init__(self, width, height):
        self.dim = (width, height)
        font = pygame.font.Font(pygame.font.get_default_font(), 20)
        font_name = 'courier' if os.name == 'nt' else 'mono'
        fonts = [x for x in pygame.font.get_fonts() if font_name in x]
        default_font = 'ubuntumono'
        mono = default_font if default_font in fonts else fonts[0]
        mono = pygame.font.match_font(mono)
        self._font_mono = pygame.font.Font(mono, 12 if os.name == 'nt' else 14)

        # Load the alert sound (Optional, ensure 'alert_sound.wav' exists or remove)
        try:
            pygame.mixer.init() # Initialize mixer
            self.alert_sound = pygame.mixer.Sound('alert_sound.wav')
            self.alert_sound.set_volume(0.5) # Optional: Adjust volume (0.0 to 1.0)
        except pygame.error as e:
            print(f"Warning: Could not load alert sound: {e}. Ensure pygame.mixer is initialized and file exists.")
            self.alert_sound = None

        # Calculate centre position for BLINKING MIDDLE notification
        # This will be passed as the initial_pos to BlinkingAlert
        notification_width = width # Full width for the blinking alert
        notification_height = 80 # Taller for a bigger, central alert
        center_x = (width - notification_width) // 2
        center_y = (height - notification_height) // 2
        # Use BlinkingAlert for critical pop-up messages
        self._blinking_alert = BlinkingAlert(font, (notification_width, notification_height), (center_x, center_y))

        # Initialize Persistent Warning (for top-right)
        self._persistent_warning = PersistentWarning(self._font_mono, self.dim, (0,0))

        self.help = HelpText(pygame.font.Font(mono, 24), width, height)
        self.server_fps = 0
        self.frame = 0
        self.simulation_time = 0
        self._show_info = True
        self._info_text = []
        self._server_clock = pygame.time.Clock()

        # Track last *count* a warning was issued to prevent continuous re-triggering for ongoing events
        self._last_collision_count_warned = 0
        self._last_lane_invasion_count_warned = 0
        self._last_speed_warning_frame_warned = -1
        self._last_lane_invasion_frame_warned = -1 # Cooldown for lane invasion notification

    def on_world_tick(self, timestamp):
        self._server_clock.tick()
        self.server_fps = self._server_clock.get_fps()
        self.frame = timestamp.frame
        self.simulation_time = timestamp.elapsed_seconds

    def tick(self, world, clock):
        # Tick custom HUD elements
        self._blinking_alert.tick(world, clock)
        self._persistent_warning.tick(world, clock) # Persistent warning does little in its tick, but it's consistent

        if not self._show_info:
            return
        
        # Original code had t, v, c and related info display. We rebuild it here.
        t = world.player.get_transform()
        v = world.player.get_velocity()
        c = world.player.get_control()
        
        # Calculate speed in km/h
        speed_kmh = 3.6 * math.sqrt(v.x**2 + v.y**2 + v.z**2)

        # Get physics control for max_rpm
        physics_control = world.player.get_physics_control()
        current_rpm = 0
        if isinstance(c, carla.VehicleControl) and physics_control:
            if c.throttle > 0.01:
                current_rpm = int(c.throttle * physics_control.max_rpm)
                current_rpm = min(current_rpm, physics_control.max_rpm)
            elif speed_kmh > 0.1:
                current_rpm = int((speed_kmh / 200.0) * (physics_control.max_rpm / 2))
                current_rpm = min(current_rpm, physics_control.max_rpm)
            else:
                current_rpm = 0

        # Get total collision and lane invasion counts
        total_collisions = world.collision_sensor.get_col_count()
        total_lane_violations = world.lane_invasion_sensor.get_invasion_count()

        # Update info text displayed on the left side
        self._info_text = [
            'SPEED:   % 10.0f KM/H' % speed_kmh,
            'RPM:     % 10.0f' % current_rpm,
            'GEAR:    % 10s' % ({-1: 'R', 0: 'N'}.get(c.gear, str(c.gear))),
            '', # Spacer
            'Total Collisions: % 8d' % total_collisions,
            'Total Lane Violations: % 8d' % total_lane_violations,
            '' # Spacer for consistency
        ]
        
        # Warning Logic - Using critical_alert for main pop-ups
        # Check for excessive speed warning (still uses frame-based cooldown as it's a continuous state)
        if speed_kmh > 120:
            if self.frame > self._last_speed_warning_frame_warned + 60: # Cooldown of 1 second (60 frames)
                self.critical_alert("EXCESSIVE SPEED!", seconds=3.0)
                self._last_speed_warning_frame_warned = self.frame
        else:
            # If speed drops below threshold, reset cooldown for speed warning
            self._last_speed_warning_frame_warned = -1 
            # Note: BlinkingAlert will fade out on its own if not re-triggered


        # Check for new collision events (triggers only when total count increases)
        # CollisionSensor._on_collision now directly calls self.hud.critical_alert
        # So, we only need to update the _last_collision_count_warned here if that's still desired for a separate warning logic,
        # otherwise, this block is mostly for HUD display.
        # The immediate trigger is from the sensor's callback.
        if total_collisions > self._last_collision_count_warned:
            # The critical_alert would have been called by the sensor already.
            # We just update the internal state for future comparisons here.
            self._last_collision_count_warned = total_collisions
        
        # Check for new lane invasion events (triggers only when total count increases AND cooldown)
        # LaneInvasionSensor._on_invasion now directly calls self.hud.critical_alert
        # So, we only need to update the _last_lane_invasion_count_warned here if that's still desired for a separate warning logic.
        if total_lane_violations > self._last_lane_invasion_count_warned:
            # Only show notification if enough time has passed since the last lane violation notification
            if self.frame > self._last_lane_invasion_frame_warned + 60: # Cooldown of 1 second (60 frames)
                self.critical_alert("LANE VIOLATION!", seconds=3.0)
                self._last_lane_invasion_count_warned = total_lane_violations # Update the count for comparison
                self._last_lane_invasion_frame_warned = self.frame # Update the frame for cooldown

    def toggle_info(self):
        self._show_info = not self._show_info

    def critical_alert(self, text, seconds=2.0, text_color=(255, 255, 255), symbol_color=(255, 255, 0)):
        """Displays a critical, blinking, bouncing alert in the center."""
        self._blinking_alert.set_text(text, text_color=text_color, seconds=seconds,
                                    symbol_enabled=True, symbol_color=symbol_color)
        if self.alert_sound:
            self.alert_sound.play()

    def notification(self, text, seconds=2.0, text_color=(255,255,255)):
        """Displays a general informational notification (no symbol, no blinking, small)."""
        # This will use BlinkingAlert but configured to look like a simple notification
        self._blinking_alert.set_text(text, text_color=text_color, seconds=seconds,
                                    symbol_enabled=False) # No symbol for general notification

    def error(self, text):
        """Displays a prominent error message."""
        self._blinking_alert.set_text('ERROR: %s' % text.upper(),
                                    text_color=(255, 0, 0), # Red text for error
                                    seconds=5.0, # Stay on screen longer
                                    symbol_enabled=True, symbol_color=(255, 0, 0)) # Red symbol for error
        if self.alert_sound:
            self.alert_sound.play()

    def render(self, display):
        if self._show_info:
            info_surface = pygame.Surface((220, self.dim[1]))
            info_surface.set_alpha(100)
            display.blit(info_surface, (0, 0))
            v_offset = 4
            bar_h_offset = 100
            bar_width = 106
            for item in self._info_text:
                if v_offset + 18 > self.dim[1]:
                    break
                if isinstance(item, list):
                    if len(item) > 1:
                        points = [(x + 8, v_offset + 8 + (1.0 - y) * 30) for x, y in enumerate(item)]
                        pygame.draw.lines(display, (255, 136, 0), False, points, 2)
                    item = None
                    v_offset += 18
                elif isinstance(item, tuple):
                    if isinstance(item[1], bool):
                        rect = pygame.Rect((bar_h_offset, v_offset + 8), (6, 6))
                        pygame.draw.rect(display, (255, 255, 255), rect, 0 if item[1] else 1)
                    else:
                        rect_border = pygame.Rect((bar_h_offset, v_offset + 8), (bar_width, 6))
                        pygame.draw.rect(display, (255, 255, 255), rect_border, 1)
                        f = (item[1] - item[2]) / (item[3] - item[2])
                        if item[2] < 0.0:
                            rect = pygame.Rect((bar_h_offset + f * (bar_width - 6), v_offset + 8), (6, 6))
                        else:
                            rect = pygame.Rect((bar_h_offset, v_offset + 8), (f * bar_width, 6))
                        pygame.draw.rect(display, (255, 255, 255), rect)
                    item = item[0]
                if item:  # At this point has to be a str.
                    surface = self._font_mono.render(item, True, (255, 255, 255))
                    display.blit(surface, (8, v_offset))
                v_offset += 18
        
        self._blinking_alert.render(display) # Render the blinking alert
        self._persistent_warning.render(display) # Render the persistent warning
        self.help.render(display)

# +------------------------------------------------------------------------------+
# | BlinkingAlert Class (MODIFIED from FadingText)                               |
# +------------------------------------------------------------------------------+

class BlinkingAlert(object): # Renamed from FadingText
    def __init__(self, font, dim, pos):
        self.font = font
        self.dim = dim # Screen dimensions
        self.initial_pos = pos # Center position (calculated by HUD)
        self.current_pos = list(pos) # Use list for mutable position
        self.seconds_left = 0
        self.surface = pygame.Surface(self.dim, pygame.SRCALPHA) # Main transparent surface
        self.text_render_surface = pygame.Surface(self.dim, pygame.SRCALPHA) # Surface to render symbol + text
        self.start_time = 0.0
        self.duration = 0.0
        self.text = "" # Store text for comparison

        # Animation parameters
        self.blink_frequency = 5.0 # Cycles per second for blinking
        self.bounce_height = 50.0  # Pixels to bounce up/down
        self.bounce_frequency = 2.0 # Bounces per second
        self.num_bounces = 3      # How many bounces before settling

        # Font for symbol, larger
        self.symbol_font = pygame.font.Font(pygame.font.get_default_font(), 40) # Even larger for middle alert

    def set_text(self, text, text_color=(255, 255, 255), seconds=2.0, symbol_enabled=True, symbol_color=(255, 255, 0)): # Added symbol_enabled
        # If the same alert is triggered again before it fades, reset its timer and re-render
        if self.text == text and self.seconds_left > 0:
            self.seconds_left = seconds # Reset timer
            self.start_time = pygame.time.get_ticks() / 1000.0
            self.current_pos = list(self.initial_pos) # Reset bounce
            return

        self.text = text # Store the text
        self.seconds_left = seconds
        self.start_time = pygame.time.get_ticks() / 1000.0
        self.duration = seconds
        self.current_pos = list(self.initial_pos) # Reset position for new alert

        # Clear previous text_render_surface
        self.text_render_surface.fill((0, 0, 0, 0))

        # Render symbol
        symbol_texture = None
        if symbol_enabled: # Only render symbol if enabled
            symbol_text = "⚠" # Unicode WARNING SIGN (triangle with exclamation)
            symbol_texture = self.symbol_font.render(symbol_text, True, symbol_color)

        # Render main text (uppercase)
        display_text = text.upper()
        text_texture = self.font.render(display_text, True, text_color)

        # Calculate total width for combined content
        total_content_width = text_texture.get_width()
        if symbol_texture:
            total_content_width += symbol_texture.get_width() + 10 # Add spacing for symbol

        total_content_height = max(symbol_texture.get_height() if symbol_texture else 0, text_texture.get_height())

        # Determine blitting positions within the text_render_surface
        blit_x_offset = (self.dim[0] - total_content_width) // 2 # Center horizontally on screen width
        symbol_y_offset = (self.dim[1] - (symbol_texture.get_height() if symbol_texture else 0)) // 2
        text_y_offset = (self.dim[1] - text_texture.get_height()) // 2


        current_blit_x = blit_x_offset
        if symbol_texture:
            self.text_render_surface.blit(symbol_texture, (current_blit_x, symbol_y_offset))
            current_blit_x += symbol_texture.get_width() + 10

        self.text_render_surface.blit(text_texture, (current_blit_x, text_y_offset))


    def tick(self, _, clock):
        delta_seconds = 1e-3 * clock.get_time()
        self.seconds_left = max(0.0, self.seconds_left - delta_seconds)

        if self.seconds_left > 0:
            elapsed_time = (pygame.time.get_ticks() / 1000.0) - self.start_time

            # Blinking (Alpha oscillation)
            alpha = int(abs(math.sin(elapsed_time * math.pi * self.blink_frequency)) * 255)
            self.surface.set_alpha(alpha) # Apply alpha to the main surface

            # Bouncing animation
            # Only bounce for a certain number of cycles at the beginning
            if elapsed_time < self.num_bounces / self.bounce_frequency:
                bounce_offset_y = self.bounce_height * (0.5 * (1 - math.cos(elapsed_time * math.pi * self.bounce_frequency * 2)))
                self.current_pos[1] = self.initial_pos[1] - bounce_offset_y
            else:
                self.current_pos[1] = self.initial_pos[1] # Settle after bounces
        else:
            self.surface.set_alpha(0) # Fully transparent when time is up

    def render(self, display):
        if self.seconds_left > 0:
            self.surface.blit(self.text_render_surface, (0, 0)) # Blit with its own internal positioning
            display.blit(self.surface, self.current_pos) # Blit the final surface with its blinking/bouncing properties
            
            
# +------------------------------------------------------------------------------+
# | HelpText Class                                                               |
# +------------------------------------------------------------------------------+

class HelpText(object):
    def __init__(self, font, width, height):
        lines = __doc__.split('\n')
        self.font = font
        self.dim = (680, len(lines) * 22 + 12)
        self.pos = (0.5 * width - 0.5 * self.dim[0], 0.5 * height - 0.5 * self.dim[1])
        self.seconds_left = 0
        self.surface = pygame.Surface(self.dim)
        self.surface.fill((0, 0, 0, 0))
        for n, line in enumerate(lines):
            text_texture = self.font.render(line, True, (255, 255, 255))
            self.surface.blit(text_texture, (22, n * 22))
            self._render = False
        self.surface.set_alpha(220)

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
        self.dim = dim # Expected to be screen dimensions
        self.pos = pos # Position for top-right corner, will be calculated by HUD
        self.text_surface = None
        self.background_color = (60, 60, 0, 150)  # Dark yellow/orange with transparency
        self.text_color = (255, 255, 255) # White text
        self.symbol_color = (255, 255, 0) # Bright yellow symbol
        self.is_active = False # Flag to show/hide the warning

        # Font for the symbol, larger than main text
        self.symbol_font = pygame.font.Font(pygame.font.get_default_font(), 24)

    def set_warning_status(self, text="", active=False):
        self.is_active = active
        if self.is_active:
            # Render symbol
            symbol_text = "⚠"
            symbol_texture = self.symbol_font.render(symbol_text, True, self.symbol_color)

            # Render text (uppercase as common for warnings)
            display_text = text.upper()
            text_texture = self.font.render(display_text, True, self.text_color)

            # Calculate total width for combined content
            total_content_width = symbol_texture.get_width() + 10 + text_texture.get_width() # Symbol + gap + text
            total_content_height = max(symbol_texture.get_height(), text_texture.get_height()) # Max height

            # Create surface for the combined warning with transparency
            self.text_surface = pygame.Surface((total_content_width + 20, total_content_height + 10), pygame.SRCALPHA) # Add padding
            self.text_surface.fill(self.background_color) # Fill with background color

            # Blit symbol and text onto this surface
            current_x_pos = 10 # Padding from left edge
            symbol_y_pos = (self.text_surface.get_height() - symbol_texture.get_height()) // 2
            text_y_pos = (self.text_surface.get_height() - text_texture.get_height()) // 2

            self.text_surface.blit(symbol_texture, (current_x_pos, symbol_y_pos))
            current_x_pos += symbol_texture.get_width() + 10

            self.text_surface.blit(text_texture, (current_x_pos, text_y_pos))
        else:
            self.text_surface = None # Clear surface when not active

    def tick(self, world, clock):
        # No complex animation needed for persistent, just update if content changes.
        # This method is primarily here to match HUD's tick expectations.
        pass

    def render(self, display):
        if self.is_active and self.text_surface:
            # Position it in the top-right corner
            render_pos_x = self.dim[0] - self.text_surface.get_width() - 10 # 10 pixel padding from right
            render_pos_y = 10 # 10 pixel padding from top
            display.blit(self.text_surface, (render_pos_x, render_pos_y))

# +------------------------------------------------------------------------------+
# | CollisionSensor Class (MODIFIED)                                             |
# +------------------------------------------------------------------------------+


class CollisionSensor(object):
    def __init__(self, parent_actor, hud):
        self.sensor = None
        self.history = []
        self._parent = parent_actor
        self.hud = hud
        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.other.collision')
        self.sensor = world.spawn_actor(bp, carla.Transform(), attach_to=self._parent)
        # We need to pass the lambda a weak reference to self to avoid circular
        # reference.
        weak_self = weakref.ref(self)
        self.sensor.listen(lambda event: CollisionSensor._on_collision(weak_self, event))

        # ADDED: Initialize collision count for HUD
        self.history_count = 0 


    def get_collision_history(self):
        history = collections.defaultdict(int)
        for frame, intensity in self.history:
            history[frame] += intensity
        return history

    # ADDED: Method to get the total collision count for HUD
    def get_col_count(self):
        return self.history_count

    @staticmethod
    def _on_collision(weak_self, event):
        self = weak_self()
        if not self:
            return
        actor_type = get_actor_display_name(event.other_actor)
        # MODIFIED: Use the HUD's critical_alert for collision notification
        self.hud.critical_alert('Collision with %r' % actor_type, seconds=2.0)
        impulse = event.normal_impulse
        intensity = math.sqrt(impulse.x**2 + impulse.y**2 + impulse.z**2)
        self.history.append((event.frame, intensity))
        if len(self.history) > 4000:
            self.history.pop(0)

        # MODIFIED: Increment history_count here directly on event
        self.history_count += 1 



# +------------------------------------------------------------------------------+
# | LaneInvasionSensor Class (MODIFIED)                                          |
# +------------------------------------------------------------------------------+


class LaneInvasionSensor(object):
    def __init__(self, parent_actor, hud):
        self.sensor = None
        self._parent = parent_actor
        self.hud = hud
        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.other.lane_invasion')
        self.sensor = world.spawn_actor(bp, carla.Transform(), attach_to=self._parent)
        # We need to pass the lambda a weak reference to self to avoid circular
        # reference.
        weak_self = weakref.ref(self)
        self.sensor.listen(lambda event: LaneInvasionSensor._on_invasion(weak_self, event))

        # ADDED: Initialize lane invasion count for HUD
        self.history_count = 0 

    # ADDED: Method to get the total lane invasion count for HUD
    def get_invasion_count(self):
        return self.history_count

    @staticmethod
    def _on_invasion(weak_self, event):
        self = weak_self()
        if not self:
            return
        lane_types = set(x.type for x in event.crossed_lane_markings)
        text = ['%r' % str(x).split()[-1] for x in lane_types]
        # MODIFIED: Use the HUD's critical_alert for lane invasion notification
        self.hud.critical_alert('Crossed line %s' % ' and '.join(text), seconds=2.0)

        # MODIFIED: Increment history_count here directly on event
        self.history_count += 1 

# +------------------------------------------------------------------------------+
# | GnssSensor Class                                                             |
# +------------------------------------------------------------------------------+


class GnssSensor(object):
    def __init__(self, parent_actor):
        self.sensor = None
        self._parent = parent_actor
        self.lat = 0.0
        self.lon = 0.0
        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.other.gnss')
        self.sensor = world.spawn_actor(bp, carla.Transform(carla.Location(x=1.0, z=2.8)), attach_to=self._parent)
        # We need to pass the lambda a weak reference to self to avoid circular
        # reference.
        weak_self = weakref.ref(self)
        self.sensor.listen(lambda event: GnssSensor._on_gnss_event(weak_self, event))

    @staticmethod
    def _on_gnss_event(weak_self, event):
        self = weak_self()
        if not self:
            return
        self.lat = event.latitude
        self.lon = event.longitude

# +------------------------------------------------------------------------------+
# | CameraManager Class                                                          |
# +------------------------------------------------------------------------------+


class CameraManager(object):
    def __init__(self, parent_actor, hud):
        self.sensor = None
        self.surface = None
        self._parent = parent_actor
        self.hud = hud
        self.recording = False
        self._camera_transforms = [
            carla.Transform(carla.Location(x=-5.5, z=2.8), carla.Rotation(pitch=-15)),
            carla.Transform(carla.Location(x=1.6, z=1.7))]
        self.transform_index = 1
        self.sensors = [
            ['sensor.camera.rgb', cc.Raw, 'Camera RGB'],
            ['sensor.camera.depth', cc.Raw, 'Camera Depth (Raw)'],
            ['sensor.camera.depth', cc.Depth, 'Camera Depth (Gray Scale)'],
            ['sensor.camera.depth', cc.LogarithmicDepth, 'Camera Depth (Logarithmic Gray Scale)'],
            ['sensor.camera.semantic_segmentation', cc.Raw, 'Camera Semantic Segmentation (Raw)'],
            ['sensor.camera.semantic_segmentation', cc.CityScapesPalette,
                'Camera Semantic Segmentation (CityScapes Palette)'],
            ['sensor.lidar.ray_cast', None, 'Lidar (Ray-Cast)']]
        world = self._parent.get_world()
        bp_library = world.get_blueprint_library()
        for item in self.sensors:
            bp = bp_library.find(item[0])
            if item[0].startswith('sensor.camera'):
                bp.set_attribute('image_size_x', str(hud.dim[0]))
                bp.set_attribute('image_size_y', str(hud.dim[1]))
                bp.set_attribute('fov', '90') # Example: Set FOV for camera sensor
            elif item[0].startswith('sensor.lidar'):
                bp.set_attribute('range', '50')
            item.append(bp)
        self.index = None

    def toggle_camera(self):
        self.transform_index = (self.transform_index + 1) % len(self._camera_transforms)
        self.sensor.set_transform(self._camera_transforms[self.transform_index])

    def set_sensor(self, index, notify=True):
        index = index % len(self.sensors)
        needs_respawn = True if self.index is None \
            else self.sensors[index][0] != self.sensors[self.index][0]
        if needs_respawn:
            if self.sensor is not None:
                self.sensor.destroy()
                self.surface = None
            self.sensor = self._parent.get_world().spawn_actor(
                self.sensors[index][-1],
                self._camera_transforms[self.transform_index],
                attach_to=self._parent)
            # We need to pass the lambda a weak reference to self to avoid
            # circular reference.
            weak_self = weakref.ref(self)
            self.sensor.listen(lambda image: CameraManager._parse_image(weak_self, image))
        if notify:
            self.hud.notification(self.sensors[index][2])
        self.index = index

    def next_sensor(self):
        self.set_sensor(self.index + 1)

    def toggle_recording(self):
        self.recording = not self.recording
        self.hud.notification('Recording %s' % ('On' if self.recording else 'Off'))

    def render(self, display):
        if self.surface is not None:
            display.blit(self.surface, (0, 0))

    @staticmethod
    def _parse_image(weak_self, image):
        self = weak_self()
        if not self:
            return
        if self.sensors[self.index][0].startswith('sensor.lidar'):
            points = np.frombuffer(image.raw_data, dtype=np.dtype('f4'))
            points = np.reshape(points, (int(points.shape[0] / 4), 4))
            lidar_data = np.array(points[:, :2])
            lidar_data *= min(self.hud.dim) / 100.0
            lidar_data += (0.5 * self.hud.dim[0], 0.5 * self.hud.dim[1])
            lidar_data = np.fabs(lidar_data) # pylint: disable=E1111
            lidar_data = lidar_data.astype(np.int32)
            lidar_data = np.reshape(lidar_data, (-1, 2))
            lidar_img_size = (self.hud.dim[0], self.hud.dim[1], 3)
            lidar_img = np.zeros(lidar_img_size)
            lidar_img[tuple(lidar_data.T)] = (255, 255, 255)
            self.surface = pygame.surfarray.make_surface(lidar_img)
        else:
            image.convert(self.sensors[self.index][1])
            array = np.frombuffer(image.raw_data, dtype=np.dtype("uint8"))
            array = np.reshape(array, (image.height, image.width, 4))
            array = array[:, :, :3]
            array = array[:, :, ::-1]
            self.surface = pygame.surfarray.make_surface(array.swapaxes(0, 1))
        if self.recording:
            image.save_to_disk('_out/%08d' % image.frame)


# +------------------------------------------------------------------------------+
# | Game Loop Function                                                           |
# +------------------------------------------------------------------------------+


def game_loop(args):
    pygame.init()
    pygame.font.init()
    world = None

    try:
        client = carla.Client(args.host, args.port)
        client.set_timeout(300.0)

        display = pygame.display.set_mode(
            (args.width, args.height),
            pygame.HWSURFACE | pygame.DOUBLEBUF)

        hud = HUD(args.width, args.height)
        world = World(client.get_world(), hud, args.filter)
        controller = DualControl(world, args.autopilot) # Use the modified DualControl

        clock = pygame.time.Clock()
        while True:
            clock.tick_busy_loop(60)
            if controller.parse_events(world, clock):
                return
            world.tick(clock) # Tick the world to advance simulation and apply controls
            world.render(display)
            pygame.display.flip()

    finally:

        if world is not None:
            world.destroy()

        pygame.quit()

# ==============================================================================
# -- main() -- function --------------------------------------------------------
# ==============================================================================
def main():
    argparser = argparse.ArgumentParser(
        description='CARLA Manual Control Client')
    argparser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='debug',
        help='print debug information')
    argparser.add_argument(
        '--host',
        metavar='H',
        default='localhost',
        help='IP of the host server (default: 127.0.0.1)')
    argparser.add_argument(
        '-p', '--port',
        metavar='P',
        default=2000,
        type=int,
        help='TCP port to listen to (default: 2000)')
    argparser.add_argument(
        '-a', '--autopilot',
        action='store_true',
        help='enable autopilot')
    argparser.add_argument(
        '--res',
        metavar='WIDTHxHEIGHT',
        default='1280x720',
        help='window resolution (default: 1280x720)')
    argparser.add_argument(
        '--filter',
        metavar='PATTERN',
        default='vehicle.*',
        help='actor filter (default: "vehicle.*")')
    argparser.add_argument(
        '--carla-root', # ADDED: Argument for CARLA root path
        metavar='PATH',
        default=os.environ.get('CARLA_ROOT', ''), # Use CARLA_ROOT env var if set
        help='Path to CARLA installation directory (e.g., /opt/carla-simulator/ or C:\\carla)')
    argparser.add_argument(
        '--no-launch-carla', # ADDED: Argument to prevent launching CARLA server
        action='store_true',
        help='Do not launch CARLA server, assume it is already running.')
    args = argparser.parse_args()

    args.width, args.height = [int(x) for x in args.res.split('x')]

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format='%(levelname)s: %(message)s', level=log_level)

    logging.info('listening to server %s:%s', args.host, args.port)

    print(__doc__)

    global carla_server_process # Declare that we are using the global variable

    try:
        # ADDED: Logic to launch CARLA server
        if not args.no_launch_carla:
            if not args.carla_root:
                logging.error("CARLA_ROOT path is not provided via --carla-root or CARLA_ROOT environment variable.")
                sys.exit(1)

            # Determine CARLA server executable path based on OS
            if sys.platform == 'win32':
                carla_server_executable = os.path.join(args.carla_root, 'WindowsNoEditor', 'CarlaUE4.exe')
                command = [carla_server_executable, f'-carla-rpc-port={args.port}']
            elif sys.platform.startswith('linux'):
                carla_server_executable = os.path.join(args.carla_root, 'CarlaUE4.sh')
                command = [carla_server_executable, f'--carla-rpc-port={args.port}']
            else:
                logging.error(f"Unsupported OS: {sys.platform}")
                sys.exit(1)

            if not os.path.exists(carla_server_executable):
                logging.error(f"CARLA server executable not found at: {carla_server_executable}")
                logging.error("Please provide the correct path to your CARLA installation root using --carla-root.")
                sys.exit(1)

            logging.info(f"Launching CARLA server: {' '.join(command)}")
            # Start the CARLA server as a subprocess
            carla_server_process = subprocess.Popen(command)

            logging.info("Waiting for CARLA server to start...")
            time.sleep(5) # Adjust this delay as needed based on your system's performance
            
            # Optional: More robust wait for server readiness (e.g., try connecting in a loop)

        game_loop(args)

    except KeyboardInterrupt:
        print('\nCancelled by user. Bye!')
    except Exception as e: # Catch broader exceptions for better error handling
        logging.error(f"An unexpected error occurred: {e}", exc_info=True) # exc_info=True to print traceback
    finally:
        # ADDED: Logic to terminate CARLA server
        if carla_server_process is not None:
            logging.info("Terminating CARLA server process...")
            carla_server_process.terminate() # Send SIGTERM
            try:
                carla_server_process.wait(timeout=5) # Wait for it to terminate
            except subprocess.TimeoutExpired:
                logging.warning("CARLA server did not terminate gracefully, forcing kill.")
                carla_server_process.kill() # Force kill if it doesn't terminate
            logging.info("CARLA server process terminated.")
        
        # Original finally block already handles pygame.quit()
        pygame.quit()


if __name__ == '__main__':

    main()

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
"""
try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg')
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64')[0]
except IndexError:
    pass
"""
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
        self.collision_sensor = CollisionSensor(self.player, self.hud)
        self.lane_invasion_sensor = LaneInvasionSensor(self.player, self.hud)
        self.gnss_sensor = GnssSensor(self.player)
        self.camera_manager = CameraManager(self.player, self.hud)
        self.camera_manager.transform_index = cam_pos_index
        self.camera_manager.set_sensor(cam_index, notify=False)
        actor_type = get_actor_display_name(self.player)
        self.hud.notification(actor_type)

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
            # Get specific vehicle physics information IN CONSTOL
            
            #print("Vehicle Transform Rotation:", vehicle_transform.rotation)
            # Define an offset for the driver's eye point (adjust these values as needed)
            driver_seat_offset_location = carla.Location(x=0.8, y=0.0, z=1.6)
            # Apply the vehicle's rotation to the offset vector using transform_vector
            rotated_offset = vehicle_transform.transform_vector(driver_seat_offset_location)
            # Add the rotated offset vector to the vehicle's world location
            spectator_location = vehicle_transform.location + rotated_offset
            # Create the spectator transform using the new location and the vehicle's rotation
            spectator_transform = carla.Transform(spectator_location, vehicle_transform.rotation)
            print(f"Vehicle Transform Rotation:, {vehicle_transform.rotation}, Vehicle Transform Location Debug info:, {vehicle_transform.location}, Spectator Offset Location {spectator_transform.location}")
            # Set the spectator's transform
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

                    # Reverse button (toggle gear between 1 and -1)
                    if event.joy == self._steer_joystick_idx and event.button == self._reverse_button_idx:
                        self._control.gear = 1 if self._control.gear else -1
                        self._control.reverse = self._control.gear < 0
                        world.hud.notification('Gear: %s' % {-1: 'R', 1: 'D'}.get(self._control.gear, self._control.gear))

                    # Manual Gear Shift (Toggle manual mode)
                    # You might map this to a button or use the 'm' key as in original
                    if event.joy == self._steer_joystick_idx and event.button == self._gear_mode_manual:
                        self._control.manual_gear_shift = not self._control.manual_gear_shift
                        self._control.gear = world.player.get_control().gear # Sync gear display
                        world.hud.notification('%s Transmission' % ('Manual' if self._control.manual_gear_shift else 'Automatic'))


                    # Gear Up (if in manual mode)
                    if self._gear_mode_manual and event.joy == self._steer_joystick_idx and event.button == self._gear_up_button_idx:
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
# | HUD Class                                                                    |
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
        
        #Calculate centre position for notification text
        notification_width = width #Assuming notification surface is full width for now
        notification_height = 40 #Based on original definition
        center_x = (width - notification_width) // 2
        center_y = (height - notification_height) // 2
        self._notifications = FadingText(font, (notification_width, notification_height), (center_x, center_y))
        self.help = HelpText(pygame.font.Font(mono, 24), width, height)
        self.server_fps = 0
        self.frame = 0
        self.simulation_time = 0
        self._show_info = True
        self._info_text = []
        self._server_clock = pygame.time.Clock()

    def on_world_tick(self, timestamp):
        self._server_clock.tick()
        self.server_fps = self._server_clock.get_fps()
        self.frame = timestamp.frame
        self.simulation_time = timestamp.elapsed_seconds

    def tick(self, world, clock):
        self._notifications.tick(world, clock)
        if not self._show_info:
            return
        t = world.player.get_transform()
        v = world.player.get_velocity()
        c = world.player.get_control()
        heading = 'N' if abs(t.rotation.yaw) < 89.5 else ''
        heading += 'S' if abs(t.rotation.yaw) > 90.5 else ''
        heading += 'E' if 179.5 > t.rotation.yaw > 0.5 else ''
        heading += 'W' if -0.5 > t.rotation.yaw > -179.5 else ''
        colhist = world.collision_sensor.get_collision_history()
        collision = [colhist[x + self.frame - 200] for x in range(0, 200)]
        max_col = max(1.0, max(collision))
        collision = [x / max_col for x in collision]
        vehicles = world.world.get_actors().filter('vehicle.*')
        self._info_text = [
            'Server:  % 16.0f FPS' % self.server_fps,
            'Client:  % 16.0f FPS' % clock.get_fps(),
            '',
            'Vehicle: % 20s' % get_actor_display_name(world.player, truncate=20),
            'Map:     % 20s' % world.world.get_map().name.split('/')[-1],
            'Simulation time: % 12s' % datetime.timedelta(seconds=int(self.simulation_time)),
            '',
            'Speed:   % 15.0f km/h' % (3.6 * math.sqrt(v.x**2 + v.y**2 + v.z**2)),
            u'Heading:% 16.0f\N{DEGREE SIGN} % 2s' % (t.rotation.yaw, heading),
            'Location:% 20s' % ('(% 5.1f, % 5.1f)' % (t.location.x, t.location.y)),
            'GNSS:% 24s' % ('(% 2.6f, % 3.6f)' % (world.gnss_sensor.lat, world.gnss_sensor.lon)),
            'Height:  % 18.0f m' % t.location.z,
            '']
        if isinstance(c, carla.VehicleControl):
            self._info_text += [
                ('Throttle:', c.throttle, 0.0, 1.0),
                ('Steer:', c.steer, -1.0, 1.0),
                ('Brake:', c.brake, 0.0, 1.0),
                ('Reverse:', c.reverse),
                ('Hand brake:', c.hand_brake),
                ('Manual:', c.manual_gear_shift),
                'Gear:        %s' % {-1: 'R', 0: 'N'}.get(c.gear, c.gear)]
        elif isinstance(c, carla.WalkerControl):
            self._info_text += [
                ('Speed:', c.speed, 0.0, 5.556),
                ('Jump:', c.jump)]
        self._info_text += [
            '',
            'Collision:',
            collision,
            '',
            'Number of vehicles: % 8d' % len(vehicles)]
        if len(vehicles) > 1:
            self._info_text += ['Nearby vehicles:']
            distance = lambda l: math.sqrt((l.x - t.location.x)**2 + (l.y - t.location.y)**2 + (l.z - t.location.z)**2)
            vehicles = [(distance(x.get_location()), x) for x in vehicles if x.id != world.player.id]
            for d, vehicle in sorted(vehicles):
                if d > 200.0:
                    break
                vehicle_type = get_actor_display_name(vehicle, truncate=22)
                self._info_text.append('% 4dm %s' % (d, vehicle_type))

    def toggle_info(self):
        self._show_info = not self._show_info

    def notification(self, text, seconds=2.0):
        self._notifications.set_text(text, text_color=(255,255,255), seconds=seconds, symbol_enabled=True, symbol_color=(255, 0, 0))

    def error(self, text):
        self._notifications.set_text('Error: %s' % text, (255, 0, 0))

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
        self._notifications.render(display)
        self.help.render(display)


# +------------------------------------------------------------------------------+
# | FadingText Class                                                             |
# +------------------------------------------------------------------------------+

class FadingText(object):
    def __init__(self, font, dim, pos):
        self.font = font
        self.dim = dim
        self.pos = pos
        self.seconds_left = 0
        self.surface = pygame.Surface(self.dim)
        self.start_time = 0.0 #To track when the notification started
        self.duration = 0.0 # How long the notification should stay
        #Adding below line for warning 
        self.symbol_font = pygame.font.Font(pygame.font.get_default_font(), 30) #Larger font symbols

    """def set_text(self, text, color=(255, 255, 255), seconds=2.0):
        text_texture = self.font.render(text, True, color)
        self.surface = pygame.Surface(self.dim)
        self.seconds_left = seconds
        self.surface.fill((0, 0, 0, 0))
        self.surface.blit(text_texture, (10, 11))
        """
    """def set_text(self, text, color=(255, 255, 255), seconds=2.0):
        text_texture = self.font.render(text, True, color)
        self.surface = pygame.Surface(self.dim, pygame.SRCALPHA) # Add SRCALPHA for transparency
        self.seconds_left = seconds
        self.surface.fill((0, 0, 0, 0))
        self.start_time = pygame.time.get_ticks() / 1000.0 #Time in seconds
        self.duration = seconds
        
        # Calculate text position within its own surface to center it
        text_x = (self.dim[0] - text_texture.get_width()) // 2
        text_y = (self.dim[1] - text_texture.get_height()) // 2
        self.surface.blit(text_texture, (text_x, text_y))
        """
        #REPLACING THE EXISTING set_text METHOD WITH THIS:
    def set_text(self, text, text_color=(255, 255, 255), seconds=2.0, symbol_enabled=False, symbol_color=(255, 0, 0)):
        self.seconds_left = seconds
        self.start_time = pygame.time.get_ticks() / 1000.0
        self.duration = seconds
        self.surface = pygame.Surface(self.dim, pygame.SRCALPHA)
        self.surface.fill((0, 0, 0, 0)) # Fill with transparent black
        # Render the symbol if enabled
        symbol_texture = None
        if symbol_enabled:
            symbol_text = "!WARNING!" # Unicode WARNING SIGN (triangle with exclamation)
            symbol_texture = self.symbol_font.render(symbol_text, True, symbol_color)
        # Render the main text (in uppercase as requested previously)
        display_text = text.upper()
        text_texture = self.font.render(display_text, True, text_color)
        # Calculate positions to center both text and symbol
        # Start with the text’s width
        total_content_width = text_texture.get_width()
        if symbol_texture:
            total_content_width += symbol_texture.get_width() + 10 # Add spacing for symbol
        # Calculate the starting X position for the combined content
        current_x_pos = (self.dim[0] - total_content_width) // 2
        # Calculate the Y position for vertical centering of both elements (adjust as needed)
        text_y_pos = (self.dim[1] - text_texture.get_height()) // 2
        symbol_y_pos = (self.dim[1] - (symbol_texture.get_height() if symbol_texture else 0)) // 2
        # Blit the symbol first if it exists
        if symbol_texture:
            self.surface.blit(symbol_texture, (current_x_pos, symbol_y_pos))
            current_x_pos += symbol_texture.get_width() + 10 # Move cursor for next item
        # Blit the text
        self.surface.blit(text_texture, (current_x_pos, text_y_pos))


    def tick(self, _, clock):
        delta_seconds = 1e-3 * clock.get_time()
        self.seconds_left = max(0.0, self.seconds_left - delta_seconds)
        #self.surface.set_alpha(500.0 * self.seconds_left)
        if self.seconds_left > 0 :
            elapsed_time = (pygame.time.get_ticks() / 1000.0) - self.start_time
            #Blinking frequency (e.g. , 5 Hz, meaning 5 full cycles per second)
            blink_frequency = 0.5
            # Alpha oscillates between 0 (fully transparent) and 255 (fully opaque)
            alpha = int(abs(math.sin(elapsed_time * math.pi * blink_frequency))* 255)
            self.surface.set_alpha(alpha)
        else:
            self.surface.set_alpha(0)
        
        

    def render(self, display):
        display.blit(self.surface, self.pos)

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
# | CollisionSensor Class                                                        |
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

    def get_collision_history(self):
        history = collections.defaultdict(int)
        for frame, intensity in self.history:
            history[frame] += intensity
        return history

    @staticmethod
    def _on_collision(weak_self, event):
        self = weak_self()
        if not self:
            return
        actor_type = get_actor_display_name(event.other_actor)
        self.hud.notification('Collision with %r' % actor_type)
        impulse = event.normal_impulse
        intensity = math.sqrt(impulse.x**2 + impulse.y**2 + impulse.z**2)
        self.history.append((event.frame, intensity))
        if len(self.history) > 4000:
            self.history.pop(0)




# +------------------------------------------------------------------------------+
# | LaneInvasionSensor Class                                                     |
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

    @staticmethod
    def _on_invasion(weak_self, event):
        self = weak_self()
        if not self:
            return
        lane_types = set(x.type for x in event.crossed_lane_markings)
        text = ['%r' % str(x).split()[-1] for x in lane_types]
        self.hud.notification('Crossed line %s' % ' and '.join(text))

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
    args = argparser.parse_args()

    args.width, args.height = [int(x) for x in args.res.split('x')]

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format='%(levelname)s: %(message)s', level=log_level)

    logging.info('listening to server %s:%s', args.host, args.port)

    print(__doc__)

    try:

        game_loop(args)

    except KeyboardInterrupt:
        print('\nCancelled by user. Bye!')

    finally:
        # Added explicit check for world and player existence before destroy
        if world is not None:
            if world.player is not None:
                # Destroy player explicitly if it exists
                world.player.destroy()
                world.player = None
            # Destroy other world objects if necessary
            # world.destroy() # World destroy might be called by World class __del__ or similar

        pygame.quit()

        

# -- run ---------------

if __name__ == '__main__':

    main()


# +------------------------------------------------------------------------------+
# | End Script - Detailed Overview and Notes Below                               |
# +------------------------------------------------------------------------------+

"""
Detailed Script Overview: 

System Hardware Setup: Ryzen 5 5600G, MSI NVIDIA RTX 3060 Ti (8GB) Ventus 2x OC, 32 GB G.Skill Ripjaw V @2133 mhz, (primary drive) Inland 1TB Gen 3x4 3D NAND M.2 NVMe SSD, ASRock B450m Pro4.

Controller Input Tested:
Brand: Fanatec CSL series [base] CSL-DD-QR2 [wheel] CSL-SW P1 V2 Steering Wheel [pedal] CSL Pedals (2-pedal base model)


Descriptions:
Pygame, the carla python package and additional value transformations are utilized to integrate Fanatec simulation hardware (model: CSL-DD/PD, Wheel and Pedal).

This script is a partial integration and modification of existing CARLA packaged script
This script integrates Fanatec DD-CSL/PD (wheel and pedal hardware kit) input, transforming data read using pygame. To drive start by pressing the brake pedal
Configure steering wheel, pedals, and buttons by setting the index variables in the DualControl class based on the output of
the joystick_input_finder.py script.

Important Note: 
Each hardware configuration _**may**_  be unique. (SEE SECTION STARTING LINE 236 FOR HARDCODING OF MAPPED INPUTS)
There are many axes, buttons and hats recognized by pygame, many of which are not relevant or produce irrelevant data. Each system must be manually configured using the additional fanatec_mapping script included in the 'FANATEC' folder.

Key Areas to work on:
- Synchronous Mode. Really important for precision and there have been many problems applying that in particular despite extended timeouts.
- Vehicle Model/Type. Each model is unique, has unique dimensions. Hoping this script maintains adaptability but that's to be seen.
- Utilization of Buttons for specific functions (paddle shifters, handbrake, etc.)

Further Work, To-Do: \n
- Test on other aspect ratios (notably DQHD - 5120x1440 - for 49" Samsung Odyssey). Running at 1280x720 or less now
- Create dynamic mapping scripts for any hardware config. for Windows AND Linux
- AUDIO! The PC has no audio output, it throws up a number of flags in the log
- Test it.....

"""
#        (┛ಠ_ಠ)┛彡┻━┻#                      This is being ported to Linux ASAP                       ┻━┻ ︵╰(°□°╰)

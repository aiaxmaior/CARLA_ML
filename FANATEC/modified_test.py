# --- Initialize persistent states ---
current_gear = 0  # Start in Neutral for manual mode
is_reverse = False
is_manual_transmission = True # Default to manual transmission
handbrake_on = False

print("\nReading configured inputs. Press Ctrl+C to exit.")
print("Press Ctrl+C to exit.")

try:
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt # Use exception to break loop
            
            if event.type == pygame.JOYBUTTONDOWN: # Process new button presses
                # Manual/Auto Toggle
                if event.joy == MANUAL_AUTO_TOGGLE_JOYSTICK_ID and event.button == MANUAL_AUTO_TOGGLE_BUTTON_ID:
                    is_manual_transmission = not is_manual_transmission
                    if not is_manual_transmission: # Switched to Auto
                        current_gear = 1 # Typically Drive in Auto
                        is_reverse = False
                    else: # Switched to Manual
                        current_gear = 0 # Neutral
                        is_reverse = False

                # Handbrake Toggle
                if event.joy == HANDBRAKE_TOGGLE_JOYSTICK_ID and event.button == HANDBRAKE_TOGGLE_BUTTON_ID:
                    handbrake_on = not handbrake_on

                if is_manual_transmission: # Gear shifts and reverse only work in manual
                    # Reverse Toggle
                    if event.joy == REVERSE_TOGGLE_JOYSTICK_ID and event.button == REVERSE_TOGGLE_BUTTON_ID:
                        is_reverse = not is_reverse
                        if is_reverse:
                            current_gear = 1 # CARLA often uses gear 1 for reverse state
                        else: # Coming out of reverse
                            current_gear = 0 # Go to Neutral

                    # Gear Up
                    if event.joy == GEAR_UP_JOYSTICK_ID and event.button == GEAR_UP_BUTTON_ID:
                        if is_reverse: # If in reverse, shifting up goes to 1st
                            is_reverse = False
                            current_gear = 1
                        elif current_gear == 0: # From Neutral to 1st
                            current_gear = 1
                        elif current_gear < MAX_FORWARD_GEARS:
                            current_gear += 1

                    # Gear Down
                    if event.joy == GEAR_DOWN_JOYSTICK_ID and event.button == GEAR_DOWN_BUTTON_ID:
                        if is_reverse: # If in reverse, shifting down goes to Neutral
                            is_reverse = False
                            current_gear = 0
                        elif current_gear > 0: # From 1st to N, or higher to lower
                            current_gear -= 1

        # Initialize control values
        steer_val = 0.0
        throttle_val = 0.0
        brake_val = 0.0
        # These states should persist across loops in a real application
        current_gear = getattr(loop_state, 'current_gear', 0) # 0=N, 1=1st, ...
        is_reverse = getattr(loop_state, 'is_reverse', False)
        is_manual_transmission = getattr(loop_state, 'is_manual_transmission', True) # Start in manual
        handbrake_on = getattr(loop_state, 'handbrake_on', False)

        # --- Axis Reading (done every frame, regardless of events) ---
        steer_val = 0.0
        throttle_val = 0.0
        brake_val = 0.0
        # Read Steering
        if STEER_JOYSTICK_ID < joystick_count and joysticks[STEER_JOYSTICK_ID].get_numaxes() > STEER_AXIS_ID:
            raw_steer = joysticks[STEER_JOYSTICK_ID].get_axis(STEER_AXIS_ID)
        elif joysticks[BRAKE_JOYSTICK_ID].get_numaxes() <= BRAKE_AXIS_ID:
            sys.stdout.write(f"Brake axis ID {BRAKE_AXIS_ID} out of range for J{BRAKE_JOYSTICK_ID}! ")

        # Process button events for state changes
        for event in pygame.event.get((pygame.JOYBUTTONDOWN)): # Only process new button presses
            # Manual/Auto Toggle
            if event.joy == MANUAL_AUTO_TOGGLE_JOYSTICK_ID and event.button == MANUAL_AUTO_TOGGLE_BUTTON_ID:
                is_manual_transmission = not is_manual_transmission
                if not is_manual_transmission: # Switched to Auto
                    current_gear = 1 # Typically Drive
                    is_reverse = False
                else: # Switched to Manual
                    current_gear = 0 # Neutral
                    is_reverse = False

            # Handbrake Toggle
            if event.joy == HANDBRAKE_TOGGLE_JOYSTICK_ID and event.button == HANDBRAKE_TOGGLE_BUTTON_ID:
                handbrake_on = not handbrake_on

            if is_manual_transmission: # Gear shifts and reverse only work in manual
                # Reverse Toggle
                if event.joy == REVERSE_TOGGLE_JOYSTICK_ID and event.button == REVERSE_TOGGLE_BUTTON_ID:
                    is_reverse = not is_reverse
                    if is_reverse:
                        current_gear = 1 # CARLA often uses gear 1 for reverse state
                    else: # Coming out of reverse
                        current_gear = 0 # Go to Neutral

                # Gear Up
                if event.joy == GEAR_UP_JOYSTICK_ID and event.button == GEAR_UP_BUTTON_ID:
                    if is_reverse: # If in reverse, shifting up goes to 1st
                        is_reverse = False
                        current_gear = 1
                    elif current_gear == 0: # From Neutral to 1st
                        current_gear = 1
                    elif current_gear < MAX_FORWARD_GEARS:
                        current_gear += 1

                # Gear Down
                if event.joy == GEAR_DOWN_JOYSTICK_ID and event.button == GEAR_DOWN_BUTTON_ID:
                    if is_reverse: # If in reverse, shifting down goes to Neutral
                        is_reverse = False
                        current_gear = 0
                    elif current_gear > 0: # From 1st to N, or higher to lower
                        current_gear -= 1

        # Store states for next iteration (simple way for this standalone script)
        class LoopState: pass
        loop_state = LoopState()
        loop_state.current_gear = current_gear
        loop_state.is_reverse = is_reverse
        loop_state.is_manual_transmission = is_manual_transmission
        loop_state.handbrake_on = handbrake_on

        # --- Output Formatting ---
        gear_display = "R" if is_reverse else (str(current_gear) if current_gear > 0 else "N")
        trans_display = "Manual" if is_manual_transmission else "Auto"

        output_string = (f"Steer: {steer_val:+.2f} | Thr: {throttle_val:.2f} | Brk: {brake_val:.2f} | "
                         f"Gear: {gear_display} ({trans_display}) | HB: {'ON' if handbrake_on else 'OFF'}")

        sys.stdout.write(" " * 150 + '\r') # Clear with spaces
        sys.stdout.write(output_string + '\r') # Write the new data
        sys.stdout.flush() # Ensure it's written to the console immediately
except:
        print("error")

#!/usr/bin/env python3
"""
PLC Toolkit - Tag Checker Tool - Module
This script reads a single tag's value and is called by the main toolkit.
It includes a continuous monitoring mode with a reading history.
"""
import json
import threading
import time
import sys
import os
from datetime import datetime
from collections import deque

# A threading event to signal the continuous scan to stop.
stop_polling_event = threading.Event()

def clear_screen():
    """Clears the terminal screen for a cleaner display."""
    os.system('cls' if os.name == 'nt' else 'clear')

def listen_for_stop():
    """
    This function runs in a background thread and waits for the user to press Enter.
    Once Enter is pressed, it sets the global stop event.
    """
    input()  # This is a blocking call that will only return when Enter is pressed.
    stop_polling_event.set()

def run_continuous_scan(plc, tag_to_read):
    """
    Starts a loop to read a tag every 5 seconds, displaying a history of the last 10 readings.
    """
    # Use a deque to efficiently store the last 10 readings.
    readings = deque(maxlen=10)
    
    # Clear any previous stop signal and start the listener thread.
    stop_polling_event.clear()
    listener_thread = threading.Thread(target=listen_for_stop, daemon=True)
    listener_thread.start()

    while not stop_polling_event.is_set():
        try:
            result = plc.read(tag_to_read)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Create a formatted string for the current reading
            output = f"[{timestamp}] Value: {result.value} (Type: {result.type}) - Error: {result.error if result.error else 'None'}"
            readings.append(output)
        except Exception as e:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            error_msg = f"[{timestamp}] [ERROR] Could not read tag: {e}"
            readings.append(error_msg)
        
        # --- Display Logic ---
        clear_screen()
        print(f"--- Monitoring '{tag_to_read}' (Last 10 Readings). Press ENTER to stop. ---")
        for reading in readings:
            print(reading)
        
        # Wait for 5 seconds. This can be interrupted by the stop event.
        stop_polling_event.wait(5)
    
    print("\n--- Continuous scan stopped. ---")


def run_checker(plc, db_conn, plc_id):
    """
    Main entry point for the tag checker tool.
    Uses the database for case-insensitive matching and the live connection for reading.
    """
    print("\n--- Tag Checker Tool ---")
    
    print("Loading tag list from local database...")
    try:
        cursor = db_conn.cursor()
        tags_json = cursor.execute('SELECT tags_json FROM tag_data WHERE plc_id = ?', (plc_id,)).fetchone()[0]
        parsed_tags_dict = json.loads(tags_json)
        tag_map = {name.lower(): definition for name, definition in parsed_tags_dict.items()}
        print("Tag list loaded.")
    except Exception as e:
        print(f"\n[ERROR] Could not load tag list from database: {e}")
        tag_map = None

    last_successful_tag = None

    while True:
        # Dynamically create the prompt based on whether we have a recent tag.
        if last_successful_tag:
            print("\n----------------------------------------------------")
            print(f"Press 'c' to continue monitoring '{last_successful_tag}'")
            print("Enter a new tag name to read another tag")
            print("Press ENTER to return to the menu")
            prompt = "Your choice: "
        else:
            prompt = "Enter tag name to read (or press ENTER to return): "
            
        tag_name_in = input(prompt).strip()

        if not tag_name_in:
            break

        # Check if user wants to start continuous scan
        if tag_name_in.lower() == 'c' and last_successful_tag:
            run_continuous_scan(plc, last_successful_tag)
            continue # After stopping, return to the prompt loop

        print(f"\nReading '{tag_name_in}'...")
        try:
            final_tag_to_read = None
            
            if tag_map:
                if '.' in tag_name_in:
                    base_tag_in, member_path_in = tag_name_in.split('.', 1)
                    parsed_def = tag_map.get(base_tag_in.lower())
                    if not parsed_def:
                        print(f"\n[ERROR] Base tag '{base_tag_in}' not found in the database.")
                        continue
                    
                    correct_base_tag = next((k for k in parsed_tags_dict if k.lower() == base_tag_in.lower()), None)

                    current_level = parsed_def
                    correct_member_path = []
                    member_found = True
                    for part in member_path_in.split('.'):
                        if isinstance(current_level, dict) and 'members' in current_level:
                            found_part = next((m for m in current_level['members'] if m.lower() == part.lower()), None)
                            if found_part:
                                correct_member_path.append(found_part)
                                current_level = current_level['members'][found_part]
                            else:
                                member_found = False; break
                        else:
                            member_found = False; break
                    
                    if member_found:
                        final_tag_to_read = f"{correct_base_tag}.{'.'.join(correct_member_path)}"
                        print(f"--> Found case-insensitive match. Reading: '{final_tag_to_read}'")
                    else:
                        print(f"\n[ERROR] Member path '.{member_path_in}' not found in tag '{correct_base_tag}'.")
                        continue
                else: # Simple tag
                    if tag_map.get(tag_name_in.lower()):
                        final_tag_to_read = next((k for k in parsed_tags_dict if k.lower() == tag_name_in.lower()), None)
                        print(f"--> Found case-insensitive match. Reading: '{final_tag_to_read}'")
                    else:
                        print(f"\n[ERROR] Tag '{tag_name_in}' not found in the database.")
                        continue
            else:
                final_tag_to_read = tag_name_in

            result = plc.read(final_tag_to_read)
            
            print("\n--- RESULT ---")
            print(f"  Tag: {result.tag}")
            print(f"Value: {result.value}")
            print(f" Type: {result.type}")
            print(f"Error: {result.error if result.error else 'None'}")
            
            if result.error is None:
                last_successful_tag = final_tag_to_read

        except Exception as e:
            print(f"\n[ERROR] An error occurred: {e}")


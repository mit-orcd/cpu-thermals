#!/usr/bin/env python3
import subprocess
import time
import re
import sys
from datetime import datetime

# ANSI color codes for terminal output
RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
RESET = '\033[0m'

def get_color(temp):
    if temp >= 90.0:
        return RED
    elif temp >= 80.0:
        return YELLOW
    return GREEN

def get_temps():
    try:
        output = subprocess.check_output(['sensors']).decode('utf-8')
    except Exception as e:
        print(f"Error running 'sensors': {e}")
        sys.exit(1)
        
    temps = []
    adapter_type = None
    
    # Parse the sensors output dynamically for both Intel and AMD
    for line in output.split('\n'):
        # Detect the adapter type for the current block
        if 'coretemp-isa' in line:
            adapter_type = 'intel'
        elif 'k10temp-pci' in line:
            adapter_type = 'amd'
            
        # Extract Intel package temperatures
        elif adapter_type == 'intel' and 'Package id' in line:
            match = re.search(r'\+([0-9.]+)', line)
            if match:
                temps.append(float(match.group(1)))
                
        # Extract AMD package temperatures
        elif adapter_type == 'amd' and 'Tctl:' in line:
            match = re.search(r'\+([0-9.]+)', line)
            if match:
                temps.append(float(match.group(1)))
                
    # Ensure we always return at least two values to avoid index out-of-range errors
    while len(temps) < 2:
        temps.append(0.0)
        
    return temps[:2]

def draw_bar(temp, min_t=40, max_t=100, width=20):
    # Clamp temperature between min_t and max_t for the graph
    t = max(min_t, min(temp, max_t))
    
    # Calculate how many block characters to draw
    fraction = (t - min_t) / (max_t - min_t)
    filled_len = int(width * fraction)
    
    # Create the visual bar
    bar = '█' * filled_len + '-' * (width - filled_len)
    return f"{get_color(temp)}{bar}{RESET}"

def main(interval):
    print(f"{'TIME':<10} | {'CPU0':<11} | {'CPU1':<11} | {'CPU0 BAR (40-100C)':<20} | {'CPU1 BAR (40-100C)':<20}")
    print("-" * 85)
    
    try:
        while True:
            temps = get_temps()
            t0, t1 = temps[0], temps[1]
            
            now = datetime.now().strftime("%H:%M:%S")
            
            t0_val = f"{t0:>5.1f}°C"
            t1_val = f"{t1:>5.1f}°C"
            
            b0 = draw_bar(t0)
            b1 = draw_bar(t1)
            
            # Print using sys.stdout to avoid ANSI codes breaking standard f-string alignment
            sys.stdout.write(f"{now:<10} | ")
            sys.stdout.write(f"{get_color(t0)}{t0_val:<11}{RESET} | ")
            sys.stdout.write(f"{get_color(t1)}{t1_val:<11}{RESET} | ")
            sys.stdout.write(f"{b0} | {b1}\n")
            sys.stdout.flush()
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == '__main__':
    # Optional: pass an interval in seconds as a command line argument (default is 2)
    interval_sec = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    main(interval_sec)

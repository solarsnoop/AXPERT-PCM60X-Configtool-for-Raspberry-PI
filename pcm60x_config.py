import os, time, serial, questionary

# --- 1. PHP LOGIC (CRC & FIXING) ---
def crc16_normal_php(buffer):
    result = 0
    for char in buffer:
        result ^= (ord(char) << 8)
        for _ in range(8):
            if (result << 1) & 0x10000:
                result = (result << 1) ^ 0x1021
            else:
                result <<= 1
            result &= 0xFFFF
    return result

def get_php_crc_bytes(cmd):
    crc_int = crc16_normal_php(cmd)
    high = (crc_int >> 8) & 0xFF
    low = crc_int & 0xFF
    def php_fix(b):
        if b in [0x0D, 0x0A, 0x28]: return b + 1
        return b
    return bytes([php_fix(high), php_fix(low)])

# --- 2. DEVICE SEARCH ---
def find_devices():
    path = "/dev/serial/by-id/"
    if not os.path.exists(path): return []
    return [os.path.join(path, f) for f in os.listdir(path) if "usb-Prolific" in f]

# --- 3. COMMUNICATION ---
def send_cmd(ser, cmd):
    ser.reset_input_buffer()
    packet = cmd.encode('ascii') + get_php_crc_bytes(cmd) + b'\x0d'
    ser.write(packet)
    time.sleep(1.2)
    return ser.read(200).decode('ascii', 'ignore').strip()

def parse_qpiri(raw):
    try:
        if not raw or '(' not in raw: return None
        parts = raw.replace('(', '').split()
        sys_v = int(parts[1])
        f = sys_v // 12 
        return {
            "max_amp": float(parts[2]),
            "bulk": float(parts[3]),
            "float": float(parts[4]),
            "factor": f,
            "system_v": sys_v
        }
    except: return None

# --- 4. MAIN PROGRAM ---
def main():
    # --- NEW: CELL COUNT INPUT ---
    cell_input = questionary.text("Enter number of cells (e.g. 7,8 or 14,16):", default="16").ask()
    if not cell_input: return
    try:
        cells = int(cell_input)
    except ValueError:
        print("Invalid number, using default 16.")
        cells = 7

    while True:
        available_devices = find_devices()
        if not available_devices:
            print("No Prolific USB adapters found!")
            break
            
        dev_path = questionary.select("Select Controller:", 
                                     choices=available_devices + ["Exit"]).ask()
        if not dev_path or dev_path == "Exit": break
        
        try:
            with serial.Serial(dev_path, 2400, timeout=3) as ser:
                while True:
                    raw_res = send_cmd(ser, "QPIRI")
                    data = parse_qpiri(raw_res)
                    
                    print("\n" + "="*60)
                    if not data:
                        print(f"   ERROR: No response from {dev_path}")
                        time.sleep(2)
                        break
                    
                    f = data['factor']
                    curr_bulk = round(data['bulk'] * f, 2)
                    curr_float = round(data['float'] * f, 2)
                    
                    print(f"   DEVICE: {dev_path}")
                    print(f"   STATUS: {data['system_v']}V System (S{cells} Config)")
                    print("-" * 60)
                    print(f"   Max Charge Current: {data['max_amp']} A")
                    print(f"   Bulk Voltage:       {curr_bulk:.2f} V  ({curr_bulk/cells:.3f} V/Cell)")
                    print(f"   Float Voltage:      {curr_float:.2f} V  ({curr_float/cells:.3f} V/Cell)")
                    print("-" * 60)
                    print(f"   Info 48V: Bulk {data['bulk']*4:.2f}V | Float {data['float']*4:.2f}V")
                    print("="*60 + "\n")

                    action = questionary.select(
                        "Select Action:", 
                        choices=["Max Current (MCHGC0)", "Bulk Voltage (PBAV)", "Float Voltage (PBFV)", "Refresh", "Switch Device", "Exit"],
                        instruction=" " 
                    ).ask()
                    
                    if not action or action == "Exit": return
                    if action == "Refresh": continue
                    if action == "Switch Device": break

                    val_input = questionary.text("Enter new value:").ask()
                    if not val_input: continue
                    
                    try:
                        new_val = float(val_input)
                        cmd, preview = "", ""

                        if "Current" in action:
                            cmd = f"MCHGC0{int(new_val):02d}"
                            preview = f"Set Current to {int(new_val)} A"
                        elif "Bulk" in action:
                            if new_val < curr_float:
                                print(f"\n[!] ERROR: Bulk < Float!"); time.sleep(2); continue
                            cmd = f"PBAV{new_val/f:.2f}"
                            preview = f"Set Bulk to {new_val:.2f}V ({new_val/cells:.3f} V/Cell)"
                        elif "Float" in action:
                            if new_val > curr_bulk:
                                print(f"\n[!] ERROR: Float > Bulk!"); time.sleep(2); continue
                            cmd = f"PBFV{new_val/f:.2f}"
                            preview = f"Set Float to {new_val:.2f}V ({new_val/cells:.3f} V/Cell)"

                        print(f"\nPREVIEW: {preview}")
                        if questionary.confirm("Send to Controller?").ask():
                            print(f"Sending: {cmd}...")
                            res = send_cmd(ser, cmd)
                            print(f"Response: {res}")
                            time.sleep(2)
                    
                    except ValueError:
                        print("Invalid number format!"); time.sleep(1)

        except Exception as e:
            print(f"Error: {e}"); time.sleep(2)

if __name__ == "__main__":
    main()

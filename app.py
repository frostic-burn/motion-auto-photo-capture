import serial
import cv2
import os
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
import threading
import time

app = Flask(__name__)

# Configuration
CAPTURE_PATH = r"C:\Users\sukhi\OneDrive\Desktop\New folder\captures"
ESP_PORT = None  # Will be set by user
ESP_BAUDRATE = 115200
ser = None
camera = None
camera_index = None
system_armed = True
latest_image = None

# Create capture directory if it doesn't exist
os.makedirs(CAPTURE_PATH, exist_ok=True)

def list_available_cameras():
    """List all available camera indices"""
    available_cameras = []
    for i in range(10):  # Check first 10 indices
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available_cameras.append(i)
            cap.release()
    return available_cameras

def list_serial_ports():
    """List available serial ports"""
    import serial.tools.list_ports
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def find_esp32_port():
    """Auto-detect ESP32 port by searching for ESP32 devices"""
    import serial.tools.list_ports
    ports = serial.tools.list_ports.comports()
    
    # Common ESP32 identifiers
    esp32_identifiers = ['CP210', 'CH340', 'UART', 'USB-SERIAL', 'USB SERIAL', 'FTDI']
    
    for port in ports:
        port_desc = port.description.upper()
        port_hwid = port.hwid.upper()
        
        # Check if port description or hardware ID contains ESP32 identifiers
        for identifier in esp32_identifiers:
            if identifier in port_desc or identifier in port_hwid:
                print(f"Found potential ESP32 device: {port.device} - {port.description}")
                return port.device
    
    return None

def initialize_camera(index):
    """Initialize camera with given index"""
    global camera
    if camera is not None:
        camera.release()
    camera = cv2.VideoCapture(index)
    if camera.isOpened():
        print(f"Camera {index} initialized successfully")
        return True
    else:
        print(f"Failed to open camera {index}")
        return False

def capture_image():
    """Capture image from camera and save to disk"""
    global latest_image
    if camera is None or not camera.isOpened():
        print("Camera not available")
        return None
    
    ret, frame = camera.read()
    if ret:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"intruder_{timestamp}.jpg"
        filepath = os.path.join(CAPTURE_PATH, filename)
        cv2.imwrite(filepath, frame)
        latest_image = filename
        print(f"Image captured: {filename}")
        return filename
    return None

def read_esp_serial():
    """Read from ESP32 serial port continuously"""
    global system_armed
    while True:
        if ser and ser.is_open:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8').strip()
                    print(f"ESP32: {line}")
                    
                    if line == "MOTION_DETECTED" and system_armed:
                        print("Motion detected! Capturing image...")
                        capture_image()
                    elif line == "ARMED":
                        system_armed = True
                    elif line == "DISARMED":
                        system_armed = False
            except Exception as e:
                print(f"Serial read error: {e}")
        time.sleep(0.1)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        'armed': system_armed,
        'latest_image': latest_image,
        'esp_connected': ser is not None and ser.is_open,
        'camera_connected': camera is not None and camera.isOpened()
    })

@app.route('/api/arm', methods=['POST'])
def arm_system():
    global system_armed
    data = request.json
    arm = data.get('arm', True)
    
    if ser and ser.is_open:
        command = "ARM\n" if arm else "DISARM\n"
        ser.write(command.encode())
        system_armed = arm
        return jsonify({'success': True, 'armed': system_armed})
    return jsonify({'success': False, 'error': 'ESP32 not connected'})

@app.route('/captures/<filename>')
def serve_capture(filename):
    return send_from_directory(CAPTURE_PATH, filename)

@app.route('/api/latest_images')
def get_latest_images():
    """Get list of latest captured images"""
    try:
        files = os.listdir(CAPTURE_PATH)
        image_files = [f for f in files if f.endswith('.jpg')]
        image_files.sort(reverse=True)
        return jsonify({'images': image_files[:10]})  # Return last 10 images
    except Exception as e:
        return jsonify({'error': str(e)})

def main():
    global ser, camera_index, ESP_PORT
    
    print("=== ESP32 Motion Detection System ===\n")
    
    # Auto-detect ESP32 port
    print("Searching for ESP32...")
    ESP_PORT = find_esp32_port()
    
    if ESP_PORT:
        print(f"✓ ESP32 found on port: {ESP_PORT}")
        use_detected = input("Use this port? (y/n): ").strip().lower()
        
        if use_detected != 'y':
            ESP_PORT = None
    
    # Manual selection if auto-detect failed or user declined
    if not ESP_PORT:
        print("\nAvailable Serial Ports:")
        ports = list_serial_ports()
        
        if not ports:
            print("No serial ports found!")
            return
        
        for i, port in enumerate(ports):
            print(f"{i+1}. {port}")
        
        port_choice = int(input("\nSelect ESP32 port number: ")) - 1
        ESP_PORT = ports[port_choice]
    
    # Select Camera
    print("\nAvailable Cameras:")
    cameras = list_available_cameras()
    for i, cam in enumerate(cameras):
        print(f"{i+1}. Camera {cam}")
    
    if not cameras:
        print("No cameras found!")
        return
    
    cam_choice = int(input("\nSelect camera number: ")) - 1
    camera_index = cameras[cam_choice]
    
    # Initialize connections
    print(f"\nConnecting to ESP32 on {ESP_PORT}...")
    ser = serial.Serial(ESP_PORT, ESP_BAUDRATE, timeout=1)
    time.sleep(2)  # Wait for ESP32 to reset
    
    print(f"Initializing camera {camera_index}...")
    if not initialize_camera(camera_index):
        print("Failed to initialize camera!")
        return
    
    # Start serial reading thread
    serial_thread = threading.Thread(target=read_esp_serial, daemon=True)
    serial_thread.start()
    
    print("\n=== System Ready ===")
    print(f"Web interface: http://localhost:5000")
    print(f"Captures saved to: {CAPTURE_PATH}")
    print("\nPress Ctrl+C to stop\n")
    
    # Start Flask server
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down...")
        if camera:
            camera.release()
        if ser:
            ser.close()
        cv2.destroyAllWindows()

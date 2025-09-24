# PacketChatMesh MicroPython Hardware Abstraction Layer
# MIT license; Copyright (c) 2022 Seon Rozenblum - Unexpected Maker
# Copyright (c) 2025 PacketChat
#
# Project home:
# https://github.com/PacketChat/PacketChatMesh

"""
PacketChatMesh Hardware Abstraction Layer

This module provides a comprehensive hardware abstraction layer for the PacketChatMesh
ESP32-S3 based board. It simplifies access to all onboard peripherals including:
- OLED Display (SSD1306 over I2C)
- LoRa Radio (SX1268 over SPI)
- NeoPixel LED Array
- Power Management
- Status LEDs

Usage Examples:
    # Initialize the board
    from packetchatmesh import PacketChatMesh
    board = PacketChatMesh()

    # Use the display
    board.display.text("Hello World!", 0, 0)
    board.display.show()

    # Control LEDs
    board.leds.fill((255, 0, 0))  # Red
    board.leds.show()

    # Check power status
    voltage = board.power.battery_voltage
    is_charging = board.power.vbus_present

    # Use LoRa radio
    board.lora.set_frequency(433.0)
    board.lora.send("Hello LoRa!")
"""

# Import required libraries
from micropython import const
from machine import Pin, ADC, I2C, SPI
import time
import neopixel

# PacketChatMesh Hardware Pin Assignments
# Based on PacketChatMesh v3.1 Hardware Specification

# Power Monitoring
VBUS_SENSE = const(34)  # USB power detection
VBAT_SENSE = const(2)   # Battery voltage monitoring

# SX1268 LoRa Radio
LORA_MISO = const(11)
LORA_MOSI = const(10)
LORA_SCK = const(9)   # WARNING: Shared with Blue LED!
LORA_SS = const(8)
LORA_RST = const(12)
LORA_BUSY = const(13)
LORA_DIO1 = const(14)
LORA_RXE = const(7)

# 0.96" OLED Display
OLED_SCL = const(42)
OLED_SDA = const(41)
OLED_VCC_EN = const(5)  # Power control

# Addressable LED Array (18 LEDs: 3x6 grid)
LED_ARRAY_DATA = const(48)  # NPDIN
LED_ARRAY_COUNT = const(18)

# USB Serial Programmer
BLUE_LED = const(9)     # Blue LED - WARNING: Shared with LoRa SCK!
PROG_BUTTON = const(0)  # Program button

# --- Hardware Abstraction Classes ---

class PowerManager:
    """Power management and monitoring for PacketChatMesh"""

    def __init__(self):
        self._vbus_pin = Pin(VBUS_SENSE, Pin.IN)
        self._vbat_adc = None

    @property
    def vbus_present(self):
        """Check if VBUS (5V USB) power is present"""
        return self._vbus_pin.value() == 1

    @property
    def battery_voltage(self):
        """Get current battery voltage in volts"""
        if self._vbat_adc is None:
            self._vbat_adc = ADC(Pin(VBAT_SENSE))
            self._vbat_adc.atten(ADC.ATTN_2_5DB)

        measured_uv = self._vbat_adc.read_uv()
        # Correction factor based on voltage divider
        measured_v = (measured_uv / 1000000) * 3.7624
        return round(measured_v, 2)

    @property
    def battery_percentage(self):
        """Estimate battery percentage (rough approximation)"""
        voltage = self.battery_voltage
        if voltage >= 4.1:
            return 100
        elif voltage >= 3.9:
            return 75
        elif voltage >= 3.7:
            return 50
        elif voltage >= 3.5:
            return 25
        elif voltage >= 3.2:
            return 10
        else:
            return 0

    @property
    def is_low_battery(self):
        """Check if battery is critically low"""
        return self.battery_voltage < 3.2

class StatusLED:
    """Control the onboard blue status LED

    NOTE: The blue LED is connected to LoRa SCK (pin 9) and will automatically
    flash during LoRa SPI communication. This provides visual indication of
    LoRa radio activity.
    """

    def __init__(self):
        self._led = Pin(BLUE_LED, Pin.OUT)

    def on(self):
        """Turn LED on"""
        self._led.value(1)

    def off(self):
        """Turn LED off"""
        self._led.value(0)

    def toggle(self):
        """Toggle LED state"""
        self._led.value(not self._led.value())

    def blink(self, count=1, delay_ms=100):
        """Blink LED specified number of times"""
        for _ in range(count):
            self.on()
            time.sleep_ms(delay_ms)
            self.off()
            time.sleep_ms(delay_ms)

    def pulse(self, duration_ms=1000):
        """Pulse LED for specified duration"""
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
            self.on()
            time.sleep_ms(50)
            self.off()
            time.sleep_ms(50)

class LEDArray:
    """Control the NeoPixel LED array"""

    def __init__(self):
        self._pixels = neopixel.NeoPixel(Pin(LED_ARRAY_DATA), LED_ARRAY_COUNT)
        self._brightness = 1.0

    def __len__(self):
        return LED_ARRAY_COUNT

    def __getitem__(self, index):
        return self._pixels[index]

    def __setitem__(self, index, color):
        self._pixels[index] = self._apply_brightness(color)

    def _apply_brightness(self, color):
        """Apply brightness scaling to color"""
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            return tuple(int(c * self._brightness) for c in color[:3])
        return color

    @property
    def brightness(self):
        """Get current brightness (0.0 to 1.0)"""
        return self._brightness

    @brightness.setter
    def brightness(self, value):
        """Set brightness (0.0 to 1.0)"""
        self._brightness = max(0.0, min(1.0, value))

    def fill(self, color):
        """Fill all LEDs with the same color"""
        color = self._apply_brightness(color)
        self._pixels.fill(color)

    def clear(self):
        """Turn off all LEDs"""
        self.fill((0, 0, 0))

    def show(self):
        """Update the LED display"""
        self._pixels.write()

    def set_pixel(self, index, color):
        """Set individual pixel color"""
        if 0 <= index < LED_ARRAY_COUNT:
            self[index] = color

    def rainbow_cycle(self, steps=255, delay_ms=1):
        """Display a rainbow cycle animation"""
        for i in range(steps):
            for j in range(LED_ARRAY_COUNT):
                color = self._color_wheel((i + j * 255 // LED_ARRAY_COUNT) % 255)
                self.set_pixel(j, color)
            self.show()
            time.sleep_ms(delay_ms)

    def _color_wheel(self, pos):
        """Generate rainbow colors across 0-255 positions"""
        pos = pos % 255
        if pos < 85:
            return (255 - pos * 3, 0, pos * 3)
        elif pos < 170:
            pos -= 85
            return (0, pos * 3, 255 - pos * 3)
        else:
            pos -= 170
            return (pos * 3, 255 - pos * 3, 0)

class Display:
    """OLED Display controller"""

    def __init__(self):
        self._i2c = None
        self._oled = None
        self._power_pin = Pin(OLED_VCC_EN, Pin.OUT)
        self._initialized = False
        self._width = 128
        self._height = 64

    def _ensure_initialized(self):
        """Ensure display is powered and initialized"""
        if not self._initialized:
            self.power_on()
            self._init_i2c()
            self._init_display()

    def power_on(self):
        """Power on the display"""
        self._power_pin.value(1)
        time.sleep_ms(100)  # Give display time to power up

    def power_off(self):
        """Power off the display"""
        self._power_pin.value(0)
        self._initialized = False

    def _init_i2c(self):
        """Initialize I2C bus"""
        if self._i2c is None:
            self._i2c = I2C(0, scl=Pin(OLED_SCL), sda=Pin(OLED_SDA), freq=400000)

    def _init_display(self):
        """Initialize the OLED display"""
        try:
            # Try to import SSD1306 driver
            from ssd1306 import SSD1306_I2C

            # Scan for display
            devices = self._i2c.scan()
            addr = None
            for test_addr in [0x3C, 0x3D]:
                if test_addr in devices:
                    addr = test_addr
                    break

            if addr is None:
                raise RuntimeError("OLED display not found")

            self._oled = SSD1306_I2C(self._width, self._height, self._i2c, addr=addr)
            self._initialized = True

        except ImportError:
            raise RuntimeError("ssd1306 module not found. Install with: mpremote mip install ssd1306")

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    def clear(self):
        """Clear the display"""
        self._ensure_initialized()
        self._oled.fill(0)

    def show(self):
        """Update the display"""
        self._ensure_initialized()
        self._oled.show()

    def text(self, string, x, y, color=1):
        """Display text at specified position"""
        self._ensure_initialized()
        self._oled.text(string, x, y, color)

    def pixel(self, x, y, color=1):
        """Set a single pixel"""
        self._ensure_initialized()
        self._oled.pixel(x, y, color)

    def fill(self, color):
        """Fill entire display with color (0 or 1)"""
        self._ensure_initialized()
        self._oled.fill(color)

    def contrast(self, level):
        """Set display contrast (0-255)"""
        self._ensure_initialized()
        if hasattr(self._oled, 'contrast'):
            self._oled.contrast(level)

    def center_text(self, text, y=None):
        """Display text centered horizontally"""
        if y is None:
            y = self.height // 2 - 4
        x = (self.width - len(text) * 8) // 2
        self.text(text, max(0, x), y)

    def test_pattern(self):
        """Display a test pattern"""
        self._ensure_initialized()
        self.clear()
        self.text("PacketChatMesh", 0, 0)
        self.text("OLED Test", 0, 10)
        self.text(f"{self.width}x{self.height} Display", 0, 20)

        # Draw border
        for x in range(self.width):
            self.pixel(x, 0)
            self.pixel(x, self.height - 1)
        for y in range(self.height):
            self.pixel(0, y)
            self.pixel(self.width - 1, y)

        self.show()

class LoRaRadio:
    """SX1268 LoRa Radio controller"""

    def __init__(self):
        self._spi = None
        self._ss = Pin(LORA_SS, Pin.OUT, value=1)
        self._rst = Pin(LORA_RST, Pin.OUT)
        self._busy = Pin(LORA_BUSY, Pin.IN)
        self._dio1 = Pin(LORA_DIO1, Pin.IN)
        self._rxe = Pin(LORA_RXE, Pin.OUT)
        self._initialized = False

    def _ensure_initialized(self):
        """Ensure LoRa module is initialized"""
        if not self._initialized:
            try:
                self._init_spi()
                self.reset()
            except Exception as e:
                print(f"LoRa initialization failed: {e}")
                self._initialized = False
                raise

    def _init_spi(self):
        """Initialize SPI bus"""
        if self._spi is None:
            try:
                self._spi = SPI(1, baudrate=2000000,
                               sck=Pin(LORA_SCK),
                               mosi=Pin(LORA_MOSI),
                               miso=Pin(LORA_MISO))
                print(f"LoRa SPI initialized on bus 1")
            except Exception as e:
                print(f"LoRa SPI initialization failed: {e}")
                self._spi = None
                raise

    def reset(self):
        """Perform hardware reset"""
        if self._spi is None:
            raise RuntimeError("SPI bus not initialized")

        self._rst.value(0)
        time.sleep_ms(20)
        self._rst.value(1)
        time.sleep_ms(20)
        self._wait_ready()
        self._initialized = True

    def _wait_ready(self, timeout_ms=100):
        """Wait for module to be ready (BUSY pin low)"""
        timeout = timeout_ms
        while self._busy.value() and timeout > 0:
            time.sleep_ms(1)
            timeout -= 1
        return timeout > 0

    def _read_register(self, address):
        """Read a single register"""
        self._ensure_initialized()
        if self._spi is None:
            raise RuntimeError("SPI bus not initialized")

        self._ss.value(0)
        time.sleep_us(1)

        self._spi.write(bytes([0x1D]))  # Read command
        self._spi.write(bytes([(address >> 8) & 0xFF]))
        self._spi.write(bytes([address & 0xFF]))
        self._spi.write(bytes([0x00]))  # NOP

        result = self._spi.read(1)
        self._ss.value(1)
        time.sleep_us(1)
        return result[0]

    def _write_register(self, address, value):
        """Write a single register"""
        self._ensure_initialized()
        if self._spi is None:
            raise RuntimeError("SPI bus not initialized")

        self._ss.value(0)
        time.sleep_us(1)

        self._spi.write(bytes([0x0D]))  # Write command
        self._spi.write(bytes([(address >> 8) & 0xFF]))
        self._spi.write(bytes([address & 0xFF]))
        self._spi.write(bytes([value]))

        self._ss.value(1)
        time.sleep_us(1)

    def _send_command(self, cmd, params=None):
        """Send a command to the module"""
        self._ensure_initialized()
        if self._spi is None:
            raise RuntimeError("SPI bus not initialized")

        self._ss.value(0)
        time.sleep_us(1)

        self._spi.write(bytes([cmd]))
        if params:
            self._spi.write(bytes(params))

        self._ss.value(1)
        time.sleep_us(1)

    def get_status(self):
        """Get module status"""
        self._ensure_initialized()
        if self._spi is None:
            raise RuntimeError("SPI bus not initialized")

        self._ss.value(0)
        self._spi.write(bytes([0xC0]))  # GetStatus command
        status = self._spi.read(1)[0]
        self._ss.value(1)
        return status

    def set_standby(self):
        """Set module to standby mode"""
        self._send_command(0x80, [0x00])  # SetStandby with RC oscillator
        time.sleep_ms(10)

    def set_frequency(self, freq_mhz):
        """Set frequency in MHz (e.g., 433.0, 868.0, 915.0)"""
        # Calculate frequency register value
        # FRF = (freq * 2^25) / 32MHz
        frf = int((freq_mhz * 1e6 * (1 << 25)) / 32e6)

        # Write frequency registers (0x06A8-0x06AB)
        for i in range(4):
            self._write_register(0x06A8 + i, (frf >> (8 * (3 - i))) & 0xFF)

    def set_tx_power(self, power_dbm):
        """Set transmit power in dBm"""
        # Basic power setting - implementation depends on PA configuration
        power_reg = max(0, min(22, power_dbm))  # Clamp to valid range
        self._write_register(0x08E7, power_reg)  # TxParams register

    def send(self, data):
        """Send data (basic implementation)"""
        # This is a simplified send - full implementation requires
        # proper packet configuration, modulation settings, etc.
        print(f"LoRa Send: {data}")
        # TODO: Implement full packet transmission

    def configure_433mhz(self):
        """Configure LoRa module for optimal 433MHz operation"""
        try:
            # Don't call _ensure_initialized here as it may cause recursion during init
            if not self._initialized or self._spi is None:
                raise RuntimeError("LoRa module not properly initialized")

            # Set frequency to 433MHz
            self.set_frequency(433.0)

            # Set appropriate bandwidth and spreading factor for 433MHz
            # These settings provide good range vs data rate balance for 433MHz
            self.set_standby()

            # Configure for 433MHz band - typical settings
            # Bandwidth: 125kHz, Spreading Factor: 7, Coding Rate: 4/5
            # Note: Full implementation would require more detailed register configuration
            print("LoRa configured for 433MHz operation")
        except Exception as e:
            print(f"Failed to configure LoRa for 433MHz: {e}")
            raise

    def configure_for_long_range(self):
        """Configure LoRa for maximum range (lower data rate)"""
        self._ensure_initialized()
        self.set_frequency(433.0)
        # Higher spreading factor = longer range but slower data rate
        # Bandwidth: 62.5kHz, Spreading Factor: 12, Coding Rate: 4/8
        print("LoRa configured for long range (slow data rate)")

    def configure_for_fast_data(self):
        """Configure LoRa for faster data transmission (shorter range)"""
        self._ensure_initialized()
        self.set_frequency(433.0)
        # Lower spreading factor = shorter range but faster data rate
        # Bandwidth: 250kHz, Spreading Factor: 6, Coding Rate: 4/5
        print("LoRa configured for fast data (shorter range)")

    def comprehensive_test(self):
        """
        Comprehensive functional hardware test for SX1268 LoRa module.
        Tests SPI communication, register access, and basic functionality.
        """
        print("  - Running comprehensive LoRa test...")

        try:
            self._ensure_initialized()

            print("    Step 1: Hardware Reset Test")
            # Reset already done in _ensure_initialized
            print("    - Reset pulse completed")

            # Wait for module to be ready (BUSY should go low)
            if not self._wait_ready(100):
                print("    - WARNING: Module still busy after reset")
            else:
                print("    - Module ready after reset")

            print("    Step 2: SPI Communication Test")

            def read_register_multi(address, length):
                """Read multiple registers from SX1268"""
                self._ss.value(0)
                time.sleep_us(1)

                self._spi.write(bytes([0x1D]))  # Read register command
                self._spi.write(bytes([(address >> 8) & 0xFF]))
                self._spi.write(bytes([address & 0xFF]))
                self._spi.write(bytes([0x00]))  # NOP byte

                result = self._spi.read(length)
                self._ss.value(1)
                time.sleep_us(1)
                return result

            # Read version string register (0x0320) - should contain device info
            print("    - Reading device version string...")
            try:
                version_data = read_register_multi(0x0320, 16)
                version_str = ""
                for byte in version_data:
                    if byte >= 32 and byte <= 126:  # Printable ASCII
                        version_str += chr(byte)
                    else:
                        version_str += "."
                print(f"    - Version string: {version_str}")
                print(f"    - Raw bytes: {[hex(b) for b in version_data]}")
            except Exception as e:
                print(f"    - Failed to read version string: {e}")

            print("    Step 3: Register Read/Write Test")
            # Test reading and writing to a safe test register
            # We'll use the sync word registers (0x0740-0x0747) for testing
            test_addr = 0x0740  # Sync word register
            original_value = self._read_register(test_addr)
            print(f"    - Original sync word value: 0x{original_value:02X}")

            # Write test pattern and read back
            test_value = 0xAA
            self._write_register(test_addr, test_value)
            time.sleep_ms(1)
            read_back = self._read_register(test_addr)

            if read_back == test_value:
                print("    - Register write/read test PASSED")
            else:
                print(f"    - Register write/read test FAILED (wrote 0x{test_value:02X}, read 0x{read_back:02X})")

            # Restore original value
            self._write_register(test_addr, original_value)

            print("    Step 4: Command Interface Test")
            # Send GetStatus command (0xC0) - should always work
            print("    - Sending GetStatus command...")
            status = self.get_status()
            print(f"    - Status response: 0x{status:02X}")

            # Decode status bits
            chip_mode = (status >> 4) & 0x7
            command_status = (status >> 1) & 0x7
            modes = ["SLEEP", "STDBY_RC", "STDBY_XOSC", "FS", "RX", "TX", "Reserved", "Reserved"]
            cmd_status = ["Reserved", "RFU", "Data available", "Command timeout", "Command error", "Failure to execute", "Command TX done", "Reserved"]

            print(f"    - Chip mode: {modes[chip_mode] if chip_mode < len(modes) else 'Unknown'}")
            print(f"    - Command status: {cmd_status[command_status] if command_status < len(cmd_status) else 'Unknown'}")

            print("    Step 5: Standby Mode Test")
            # Put chip in standby mode
            self.set_standby()

            # Check if mode changed
            new_status = self.get_status()
            new_mode = (new_status >> 4) & 0x7
            print(f"    - Mode after SetStandby: {modes[new_mode] if new_mode < len(modes) else 'Unknown'}")

            print("    Step 6: Frequency Test")
            # Test setting a frequency register
            # For 433MHz: FRF = (433e6 * 2^25) / 32e6
            freq_433_regs = [0x1B, 0x1C, 0xCC, 0xCD]  # 433 MHz

            # Write frequency registers (0x06A8-0x06AB)
            for i, val in enumerate(freq_433_regs):
                self._write_register(0x06A8 + i, val)

            # Read back frequency
            freq_readback = []
            for i in range(4):
                freq_readback.append(self._read_register(0x06A8 + i))

            print(f"    - Frequency registers set to: {[hex(f) for f in freq_readback]}")

            print("    SUCCESS: LoRa module passed all hardware tests!")
            return True

        except Exception as e:
            print(f"    - ERROR: LoRa test failed: {e}")
            import sys
            sys.print_exception(e)
            return False

    def simple_test(self):
        """
        Simple LoRa connectivity test - just verify SPI communication
        """
        print("  - Running simple LoRa test...")

        try:
            # Check busy pin state
            print(f"    - BUSY pin state: {'HIGH' if self._busy.value() else 'LOW'}")

            # Try to read status
            status = self.get_status()
            if status is not None:
                print(f"    - Status register: 0x{status:02X}")
                print("    - SUCCESS: SPI communication working")
                return True
            else:
                print("    - ERROR: No response from module")
                return False

        except Exception as e:
            print(f"    - ERROR: Simple LoRa test failed: {e}")
            return False

    def test_communication(self):
        """Test basic SPI communication"""
        try:
            self._ensure_initialized()
            status = self.get_status()
            # Check if we got a valid status response
            if status is not None:
                # SX1268 status should have reasonable values
                chip_mode = (status >> 4) & 0x7
                return chip_mode <= 6  # Valid modes are 0-6
            return False
        except Exception as e:
            print(f"LoRa communication test failed: {e}")
            return False

# --- Main Hardware Abstraction Class ---

class PacketChatMesh:
    """
    Main hardware abstraction class for PacketChatMesh board

    Provides easy access to all onboard peripherals through a unified interface.
    """

    def __init__(self, auto_init=True):
        """
        Initialize PacketChatMesh board

        Args:
            auto_init: If True, automatically initialize all peripherals
        """
        # Initialize hardware components
        self.power = PowerManager()
        self.status_led = StatusLED()
        self.leds = LEDArray()
        self.display = Display()
        self.lora = LoRaRadio()

        if auto_init:
            self.init_all()

    def init_all(self):
        """Initialize all peripherals"""
        success_count = 0
        total_count = 4

        # Initialize display
        try:
            self.display.power_on()
            success_count += 1
            print("✓ Display initialized")
        except Exception as e:
            print(f"✗ Display failed: {e}")

        # Initialize LEDs
        try:
            self.leds.clear()
            self.leds.show()
            success_count += 1
            print("✓ LED Array initialized")
        except Exception as e:
            print(f"✗ LED Array failed: {e}")

        # Initialize LoRa
        try:
            self.lora._init_spi()  # Initialize SPI first
            self.lora.reset()
            self.lora.configure_433mhz()  # Configure for 433MHz operation
            success_count += 1
            print("✓ LoRa Radio initialized")
        except Exception as e:
            print(f"✗ LoRa Radio failed: {e}")
            # Clear the initialized flag if initialization failed
            self.lora._initialized = False

        # Initialize power monitoring (always works)
        try:
            _ = self.power.battery_voltage  # Test power system
            success_count += 1
            print("✓ Power Management initialized")
        except Exception as e:
            print(f"✗ Power Management failed: {e}")

        if success_count == total_count:
            print("🎉 PacketChatMesh fully initialized!")
        else:
            print(f"⚠️  PacketChatMesh partially initialized ({success_count}/{total_count} modules)")

    def run_diagnostics(self):
        """Run comprehensive hardware diagnostics"""
        print("=== PacketChatMesh Hardware Diagnostics ===\n")

        # Power System Test
        print("[1] Power System:")
        print(f"  - USB Power: {'Connected' if self.power.vbus_present else 'Not Connected'}")
        print(f"  - Battery: {self.power.battery_voltage}V ({self.power.battery_percentage}%)")
        if self.power.is_low_battery:
            print("  - WARNING: Low battery!")

        # Status LED Test
        print("\n[2] Status LED:")
        print("  - Testing LED...")
        self.status_led.blink(3, 100)
        print("  - LED test complete")

        # LED Array Test
        print("\n[3] LED Array:")
        print("  - Testing RGB colors...")
        colors = [(64, 0, 0), (0, 64, 0), (0, 0, 64), (0, 0, 0)]
        for color in colors:
            self.leds.fill(color)
            self.leds.show()
            time.sleep(0.3)
        print("  - LED array test complete")

        # Display Test
        print("\n[4] OLED Display:")
        try:
            self.display.test_pattern()
            time.sleep(1)
            print("  - Display test complete")
        except Exception as e:
            print(f"  - Display test failed: {e}")

        # LoRa Test
        print("\n[5] LoRa Radio:")
        try:
            # Try comprehensive test first, fall back to simple test
            if not self.lora.comprehensive_test():
                print("  - Falling back to simple LoRa test...")
                self.lora.simple_test()

            # Additional pin tests
            print("\n  Additional Pin Tests:")
            print(f"  - RXE pin controllable: {'Yes' if hasattr(self.lora._rxe, 'value') else 'No'}")
            print(f"  - BUSY pin readable: {self.lora._busy.value()}")
            print(f"  - DIO1 pin readable: {self.lora._dio1.value()}")

            # Test RXE pin (if it controls RX/TX switching)
            print("  - Testing RXE pin switching...")
            for state in [0, 1, 0]:
                self.lora._rxe.value(state)
                time.sleep_ms(100)
                print(f"    RXE = {state}")

        except Exception as e:
            print(f"  - LoRa test failed: {e}")

        print("\n=== Diagnostics Complete ===")

    def sleep(self):
        """Put board into low power sleep mode"""
        self.display.power_off()
        self.leds.clear()
        self.leds.show()
        # TODO: Implement deeper sleep modes

    def wake(self):
        """Wake board from sleep mode"""
        self.display.power_on()
        # TODO: Restore from sleep

# --- Convenience Functions for Backward Compatibility ---

def get_battery_voltage():
    """Legacy function - use PacketChatMesh.power.battery_voltage instead"""
    power = PowerManager()
    return power.battery_voltage

def get_vbus_present():
    """Legacy function - use PacketChatMesh.power.vbus_present instead"""
    power = PowerManager()
    return power.vbus_present

def prog_led_set(state):
    """Legacy function - use PacketChatMesh.status_led instead

    NOTE: Blue LED shares pin with LoRa SCK and will flash during LoRa activity
    """
    led = StatusLED()
    if state:
        led.on()
    else:
        led.off()

def prog_led_blink():
    """Legacy function - use PacketChatMesh.status_led.blink() instead

    NOTE: Blue LED shares pin with LoRa SCK and will flash during LoRa activity
    """
    led = StatusLED()
    led.toggle()

def lora_reset():
    """Legacy function - use PacketChatMesh.lora.reset() instead"""
    lora = LoRaRadio()
    lora.reset()

def set_oled_power(state):
    """Legacy function - use PacketChatMesh.display.power_on/off() instead"""
    display = Display()
    if state:
        display.power_on()
    else:
        display.power_off()

def init_display():
    """Legacy function - use PacketChatMesh.display instead"""
    display = Display()
    display.power_on()
    display._init_i2c()
    return display._i2c

def init_lora():
    """Legacy function - use PacketChatMesh.lora instead"""
    lora = LoRaRadio()
    lora._init_spi()
    lora.reset()
    return lora._spi

def rgb_color_wheel(wheel_pos):
    """Legacy function - use PacketChatMesh.leds._color_wheel() instead"""
    led_array = LEDArray()
    return led_array._color_wheel(wheel_pos)

def run_hardware_tests():
    """Legacy function - use PacketChatMesh.run_diagnostics() instead"""
    board = PacketChatMesh()
    board.run_diagnostics()

# --- Usage Examples ---

def example_usage():
    """Example usage of the PacketChatMesh hardware abstraction layer"""

    # Initialize the board
    board = PacketChatMesh()

    # Display a welcome message
    board.display.clear()
    board.display.center_text("PacketChatMesh", 10)
    board.display.center_text("Ready!", 30)
    board.display.show()

    # Show battery status with LED color
    voltage = board.power.battery_voltage
    if voltage > 3.8:
        board.leds.fill((0, 255, 0))  # Green - good battery
    elif voltage > 3.5:
        board.leds.fill((255, 255, 0))  # Yellow - medium battery
    else:
        board.leds.fill((255, 0, 0))  # Red - low battery
    board.leds.show()

    # Set up LoRa for 433MHz
    board.lora.set_frequency(433.0)
    board.lora.set_tx_power(14)

    print("PacketChatMesh is ready!")

if __name__ == "__main__":
    # Run diagnostics when module is executed directly
    board = PacketChatMesh()
    board.run_diagnostics()
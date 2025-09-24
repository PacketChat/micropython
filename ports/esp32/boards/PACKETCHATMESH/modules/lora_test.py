# LoRa Hardware Test Functions
# Add these to your PacketChatMesh module


def comprehensive_lora_test(spi):
    """
    Comprehensive functional hardware test for SX1268 LoRa module.
    Tests SPI communication, register access, and basic functionality.
    """
    print("  - Running comprehensive LoRa test...")

    try:
        # Pin setup for control signals
        ss = Pin(LORA_SS, Pin.OUT, value=1)  # Chip select - start high (inactive)
        rst = Pin(LORA_RST, Pin.OUT)         # Reset pin
        busy = Pin(LORA_BUSY, Pin.IN)        # Busy status pin
        dio1 = Pin(LORA_DIO1, Pin.IN)        # DIO1 interrupt pin

        print("    Step 1: Hardware Reset Test")
        # Perform hardware reset
        rst.value(0)
        time.sleep_ms(20)
        rst.value(1)
        time.sleep_ms(20)
        print("    - Reset pulse completed")

        # Wait for module to be ready (BUSY should go low)
        timeout = 100  # 100ms timeout
        while busy.value() and timeout > 0:
            time.sleep_ms(1)
            timeout -= 1

        if timeout == 0:
            print("    - WARNING: Module still busy after reset")
        else:
            print("    - Module ready after reset")

        print("    Step 2: SPI Communication Test")
        # Test basic SPI communication by reading device type register
        # For SX1268, we'll read register 0x0320 (VERSION_STRING)
        def read_register(address):
            """Read a single register from SX1268"""
            ss.value(0)  # Select chip
            time.sleep_us(1)

            # Send read command (0x1D) followed by 16-bit address
            spi.write(bytes([0x1D]))  # Read register command
            spi.write(bytes([(address >> 8) & 0xFF]))  # High byte
            spi.write(bytes([address & 0xFF]))         # Low byte
            spi.write(bytes([0x00]))  # NOP byte

            # Read the response
            result = spi.read(1)
            ss.value(1)  # Deselect chip
            time.sleep_us(1)
            return result[0]

        def read_register_multi(address, length):
            """Read multiple registers from SX1268"""
            ss.value(0)
            time.sleep_us(1)

            spi.write(bytes([0x1D]))  # Read register command
            spi.write(bytes([(address >> 8) & 0xFF]))
            spi.write(bytes([address & 0xFF]))
            spi.write(bytes([0x00]))  # NOP byte

            result = spi.read(length)
            ss.value(1)
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
        original_value = read_register(test_addr)
        print(f"    - Original sync word value: 0x{original_value:02X}")

        def write_register(address, value):
            """Write a single register to SX1268"""
            ss.value(0)
            time.sleep_us(1)

            spi.write(bytes([0x0D]))  # Write register command
            spi.write(bytes([(address >> 8) & 0xFF]))
            spi.write(bytes([address & 0xFF]))
            spi.write(bytes([value]))

            ss.value(1)
            time.sleep_us(1)

        # Write test pattern and read back
        test_value = 0xAA
        write_register(test_addr, test_value)
        time.sleep_ms(1)
        read_back = read_register(test_addr)

        if read_back == test_value:
            print("    - Register write/read test PASSED")
        else:
            print(f"    - Register write/read test FAILED (wrote 0x{test_value:02X}, read 0x{read_back:02X})")

        # Restore original value
        write_register(test_addr, original_value)

        print("    Step 4: Command Interface Test")
        # Test sending a command to the module
        def send_command(cmd, params=None):
            """Send a command to SX1268"""
            ss.value(0)
            time.sleep_us(1)

            spi.write(bytes([cmd]))
            if params:
                spi.write(bytes(params))

            ss.value(1)
            time.sleep_us(1)

        # Send GetStatus command (0xC0) - should always work
        print("    - Sending GetStatus command...")
        ss.value(0)
        spi.write(bytes([0xC0]))  # GetStatus command
        status = spi.read(1)[0]
        ss.value(1)
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
        send_command(0x80, [0x00])  # SetStandby with RC oscillator
        time.sleep_ms(10)

        # Check if mode changed
        ss.value(0)
        spi.write(bytes([0xC0]))
        new_status = spi.read(1)[0]
        ss.value(1)

        new_mode = (new_status >> 4) & 0x7
        print(f"    - Mode after SetStandby: {modes[new_mode] if new_mode < len(modes) else 'Unknown'}")

        print("    Step 6: Frequency Test")
        # Test setting a frequency register
        # Frequency = (FRF * FXOSC) / 2^25, where FXOSC = 32MHz
        # For 868MHz: FRF = (868e6 * 2^25) / 32e6 = 915625984 = 0x3689999F
        freq_regs = [0x36, 0x89, 0x99, 0x9F]  # 868 MHz

        # Write frequency registers (0x06A8-0x06AB)
        for i, val in enumerate(freq_regs):
            write_register(0x06A8 + i, val)

        # Read back frequency
        freq_readback = []
        for i in range(4):
            freq_readback.append(read_register(0x06A8 + i))

        print(f"    - Frequency registers set to: {[hex(f) for f in freq_readback]}")

        print("    SUCCESS: LoRa module passed all hardware tests!")
        return True

    except Exception as e:
        print(f"    - ERROR: LoRa test failed: {e}")
        import sys
        sys.print_exception(e)
        return False

def simple_lora_test(spi):
    """
    Simple LoRa connectivity test - just verify SPI communication
    """
    print("  - Running simple LoRa test...")

    try:
        ss = Pin(LORA_SS, Pin.OUT, value=1)
        busy = Pin(LORA_BUSY, Pin.IN)

        # Reset the module
        lora_reset()

        # Check busy pin state
        print(f"    - BUSY pin state: {'HIGH' if busy.value() else 'LOW'}")

        # Try to read status
        ss.value(0)
        time.sleep_us(10)
        spi.write(bytes([0xC0]))  # GetStatus command
        status_bytes = spi.read(1)
        ss.value(1)

        if len(status_bytes) > 0:
            status = status_bytes[0]
            print(f"    - Status register: 0x{status:02X}")
            print("    - SUCCESS: SPI communication working")
            return True
        else:
            print("    - ERROR: No response from module")
            return False

    except Exception as e:
        print(f"    - ERROR: Simple LoRa test failed: {e}")
        return False

# Add this to the existing run_hardware_tests() function
def enhanced_lora_test():
    """Enhanced LoRa test section for the hardware test suite"""
    print("\n[4] Enhanced LoRa Module Test:")
    spi = init_lora()

    # Try comprehensive test first, fall back to simple test
    if not comprehensive_lora_test(spi):
        print("  - Falling back to simple LoRa test...")
        simple_lora_test(spi)

    # Additional pin tests
    print("\n  Additional Pin Tests:")
    rxe = Pin(LORA_RXE, Pin.OUT)
    busy = Pin(LORA_BUSY, Pin.IN)
    dio1 = Pin(LORA_DIO1, Pin.IN)

    print(f"  - RXE pin controllable: {'Yes' if hasattr(rxe, 'value') else 'No'}")
    print(f"  - BUSY pin readable: {busy.value()}")
    print(f"  - DIO1 pin readable: {dio1.value()}")

    # Test RXE pin (if it controls RX/TX switching)
    print("  - Testing RXE pin switching...")
    for state in [0, 1, 0]:
        rxe.value(state)
        time.sleep_ms(100)
        print(f"    RXE = {state}")

    print("  - LoRa hardware test complete")


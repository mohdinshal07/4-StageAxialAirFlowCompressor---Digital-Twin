"""Optional hardware link to the ESP32 / Arduino UNO R4 WiFi over USB serial (pyserial).
Protocol (one line per sample, 10 Hz, from the board):
    D,<T_amb_C>,<P_amb_Pa>,<T_out_C>,<p_out_static_Pa>,<rpm>
Command sent by the twin to the board (forwarded to the motor driver):
    R,<rpm>
"""
import threading

class SerialRig:
    def __init__(self, port, baud=115200):
        import serial                                  # pip install pyserial
        self.ser = serial.Serial(port, baud, timeout=0.05)
        self.latest = None; self.lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        buf = b''
        while True:
            buf += self.ser.read(256)
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                p = line.decode(errors='ignore').strip().split(',')
                if len(p) == 6 and p[0] == 'D':
                    try:
                        T_amb, P_amb, T_out, p_out, N = map(float, p[1:])
                        with self.lock:
                            self.latest = dict(T_amb=T_amb + 273.15, P_amb=P_amb, T_out=T_out + 273.15, p_out_static=p_out, N=N)
                    except ValueError:
                        pass

    def read(self):
        with self.lock: return dict(self.latest) if self.latest else None

    def write_rpm(self, rpm):
        self.ser.write(('R,%d\n' % round(rpm)).encode())

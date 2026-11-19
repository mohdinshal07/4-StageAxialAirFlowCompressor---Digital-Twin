/*
  4-stage compressor test rig  -  Arduino UNO R4 WiFi (ESP32-S3 on board) firmware
  -----------------------------------------------------------------------------
  Reads the rig sensors, streams them to the digital twin (PC, USB serial) and
  forwards the twin's speed command to the VESC motor controller.

  Hardware (see hardware list):
    - Ambient pressure : Adafruit LPS33HW  (I2C, address 0x5D, default)
    - Outlet pressure  : Adafruit LPS33HW  (I2C, address 0x5C: SDO pin -> GND), port connected by a
                         silicone tube to a static-pressure tap of the outlet spool
    - Ambient temp.    : PT100 probe + Adafruit MAX31865 (SPI, CS = D10), 3-wire
    - Outlet temp.     : PT100 probe (3 mm) + Adafruit MAX31865 (SPI, CS = D9), 3-wire, in the spool
                         thermocouple boss
    - Motor controller : Flipsky 75100 (VESC) on Serial1 (D0 RX / D1 TX). VESC UART is 3.3 V:
                         put a 1k/2k divider on UNO TX -> VESC RX.  App setting in VESC Tool: UART, 115200 baud.

  Libraries (Arduino Library Manager): Adafruit LPS35HW, Adafruit MAX31865, Adafruit BusIO, VescUart (SolidGeek).

  PC protocol (USB serial, 115200 baud):
    board -> PC : D,<T_amb_C>,<P_amb_Pa>,<T_out_C>,<p_out_static_Pa>,<rpm>      (10 Hz)
    PC -> board : R,<rpm>                                                         (speed command)
  Safety: if no command is received for 1 s the motor is commanded to 0 rpm.

  NOTE: written without the hardware at hand - check every sensor with the library example sketches first.
*/
#include <Wire.h>
#include <SPI.h>
#include <Adafruit_LPS35HW.h>
#include <Adafruit_MAX31865.h>
#include <VescUart.h>

#define RREF      430.0     // MAX31865 reference resistor for PT100 (Adafruit board)
#define RNOMINAL  100.0     // PT100
#define POLE_PAIRS 2        // 4-pole inrunner motor: ERPM = 2 x RPM
#define RPM_MAX   25000

Adafruit_LPS35HW lpsAmb, lpsOut;
Adafruit_MAX31865 rtdAmb(10), rtdOut(9);
VescUart vesc;

float rpmCmd = 0;
unsigned long lastCmd = 0, lastTx = 0;
String rx;

void setup() {
  Serial.begin(115200);
  Serial1.begin(115200);
  vesc.setSerialPort(&Serial1);
  Wire.begin();
  if (!lpsAmb.begin_I2C(0x5D)) Serial.println("# ambient LPS33HW not found");
  if (!lpsOut.begin_I2C(0x5C)) Serial.println("# outlet LPS33HW not found");
  rtdAmb.begin(MAX31865_3WIRE);
  rtdOut.begin(MAX31865_3WIRE);
}

void handleCommand(const String &s) {
  if (s.startsWith("R,")) {
    rpmCmd = constrain(s.substring(2).toFloat(), 0, RPM_MAX);
    lastCmd = millis();
  }
}

void loop() {
  // ---- commands from the twin
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { handleCommand(rx); rx = ""; } else if (c != '\r') rx += c;
  }
  if (millis() - lastCmd > 1000) rpmCmd = 0;            // watchdog
  // ---- 10 Hz: send speed set point to the VESC and stream the measurements
  if (millis() - lastTx >= 100) {
    lastTx = millis();
    vesc.setRPM(rpmCmd * POLE_PAIRS);                    // VESC speed loop works in electrical rpm
    float rpm = 0;
    if (vesc.getVescValues()) rpm = vesc.data.rpm / POLE_PAIRS;
    float pAmb = lpsAmb.readPressure() * 100.0;          // library returns hPa -> Pa (check with the example sketch)
    float pOut = lpsOut.readPressure() * 100.0;
    float tAmb = rtdAmb.temperature(RNOMINAL, RREF);
    float tOut = rtdOut.temperature(RNOMINAL, RREF);
    Serial.print("D,");
    Serial.print(tAmb, 2); Serial.print(',');
    Serial.print(pAmb, 0); Serial.print(',');
    Serial.print(tOut, 2); Serial.print(',');
    Serial.print(pOut, 0); Serial.print(',');
    Serial.println(rpm, 0);
  }
}

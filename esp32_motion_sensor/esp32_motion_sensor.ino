#define PIR_PIN 13   // PIR output connected to GPIO 13

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
}

void loop() {
  int pirState = digitalRead(PIR_PIN);

  if (pirState == HIGH) {
    Serial.println("Motion detected!");
  } else {
    Serial.println("No motion");
  }

  delay(200);  // small debounce/read delay
}

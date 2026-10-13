import 'package:flutter_test/flutter_test.dart';
import 'package:odtu_reservation/main.dart';

void main() {
  test('starter build has push disabled until Firebase is configured', () {
    expect(pushBuildEnabled, false);
  });
}

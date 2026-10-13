import 'dart:async';
import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';

// Replaced by `flutterfire configure` when push messaging is configured.
import 'firebase_options.dart';

// Allows an initial APK to run without an account or fabricated Firebase keys.
// Build with --dart-define=ENABLE_PUSH=true only after real Firebase setup.
const bool pushBuildEnabled = bool.fromEnvironment('ENABLE_PUSH', defaultValue: false);
bool pushInitialized = false;
String pushStartupError = '';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (pushBuildEnabled) {
    try {
      await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
      pushInitialized = true;
    } catch (e) {
      pushStartupError = 'Firebase başlatılamadı: $e';
    }
  }
  runApp(const ReservationApp());
}

class ReservationApp extends StatelessWidget {
  const ReservationApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'ODTÜ Spor Rezervasyon',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF124B63),
          primary: const Color(0xFF124B63),
          surface: const Color(0xFFF7F9FA),
        ),
        scaffoldBackgroundColor: const Color(0xFFF7F9FA),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        ),
      ),
      home: const ReservationHome(),
    );
  }
}

class ReservationHome extends StatefulWidget {
  const ReservationHome({super.key});

  @override
  State<ReservationHome> createState() => _ReservationHomeState();
}

class _ReservationHomeState extends State<ReservationHome>
    with WidgetsBindingObserver {
  final storage = const FlutterSecureStorage();
  final facilityController = TextEditingController(text: 'Spor Merkezi');
  final serverController = TextEditingController();
  final keyController = TextEditingController();
  DateTime date = DateTime.now().add(const Duration(days: 1));
  TimeOfDay time = const TimeOfDay(hour: 18, minute: 0);
  bool busy = false;
  bool showingSetup = false;
  String status = 'IDLE';
  String lastMessage = 'Henüz takip başlatılmadı.';
  String lastChecked = '';
  String error = '';
  Timer? refreshTimer;
  StreamSubscription<String>? tokenSubscription;
  StreamSubscription<RemoteMessage>? onMessageSubscription;
  StreamSubscription<RemoteMessage>? openedSubscription;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initialize();
  }

  Future<void> _initialize() async {
    serverController.text = await storage.read(key: 'api_url') ?? '';
    keyController.text = await storage.read(key: 'api_key') ?? '';
    if (!mounted) return;
    setState(() {
      showingSetup = serverController.text.isEmpty;
    });
    if (pushInitialized) {
    onMessageSubscription = FirebaseMessaging.onMessage.listen((message) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message.notification?.body ?? 'Rezervasyon bildirimi geldi.')),
      );
      _refresh();
    });
    openedSubscription = FirebaseMessaging.onMessageOpenedApp.listen((_) => _refresh());
    tokenSubscription = FirebaseMessaging.instance.onTokenRefresh.listen((_) => _registerToken());
    }
    refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) => _refresh());
    await _refresh();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    refreshTimer?.cancel();
    tokenSubscription?.cancel();
    onMessageSubscription?.cancel();
    openedSubscription?.cancel();
    facilityController.dispose();
    serverController.dispose();
    keyController.dispose();
    super.dispose();
  }

  Uri _uri(String path) {
    final base = serverController.text.trim().replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(base);
    final isLoopback = uri != null &&
        (uri.host == 'localhost' || uri.host == '127.0.0.1' || uri.host == '10.0.2.2');
    if (uri == null || !uri.hasAuthority ||
        (uri.scheme != 'https' && !(uri.scheme == 'http' && isLoopback))) {
      throw Exception('Use an HTTPS backend URL (HTTP only for localhost/emulator).');
    }
    return Uri.parse('$base$path');
  }

  Future<Map<String, dynamic>> _api(String method, String path,
      [Map<String, dynamic>? body]) async {
    final headers = <String, String>{
      'X-API-Key': keyController.text.trim(),
      'Content-Type': 'application/json',
    };
    late http.Response response;
    final uri = _uri(path);
    if (method == 'POST') {
      response = await http.post(uri, headers: headers, body: jsonEncode(body ?? {}))
          .timeout(const Duration(seconds: 25));
    } else {
      response = await http.get(uri, headers: headers)
          .timeout(const Duration(seconds: 25));
    }
    final json = jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode >= 400) {
      throw Exception(json is Map ? (json['detail'] ?? 'Request failed') : 'Request failed');
    }
    return Map<String, dynamic>.from(json as Map);
  }

  Future<void> _saveConnection() async {
    setState(() => busy = true);
    try {
      await storage.write(key: 'api_url', value: serverController.text.trim());
      await storage.write(key: 'api_key', value: keyController.text.trim());
      final result = await _api('GET', '/status');
      await _registerToken();
      if (!mounted) return;
      setState(() {
        showingSetup = false;
        error = '';
      });
      _acceptStatus(result);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _registerToken() async {
    if (!pushInitialized) return;
    // Request permission from a user interaction during connection/setup.
    try {
      final settings = await FirebaseMessaging.instance.requestPermission(
        alert: true, sound: true, badge: true,
      );
      if (settings.authorizationStatus == AuthorizationStatus.denied) return;
      final deviceToken = await FirebaseMessaging.instance.getToken();
      if (deviceToken != null && serverController.text.isNotEmpty && keyController.text.isNotEmpty) {
        await _api('POST', '/device', {'token': deviceToken});
      }
    } catch (e) {
      if (mounted) setState(() => error = 'Bildirim kaydı başarısız: $e');
    }
  }

  void _acceptStatus(Map<String, dynamic> data) {
    if (!mounted) return;
    setState(() {
      status = '${data['status'] ?? 'IDLE'}';
      lastMessage = '${data['last_message'] ?? ''}';
      lastChecked = '${data['last_checked'] ?? ''}';
      final job = data['job'];
      if (job is Map) {
        facilityController.text = '${job['facility'] ?? facilityController.text}';
        final parsedDate = DateTime.tryParse('${job['date'] ?? ''}');
        if (parsedDate != null) date = parsedDate;
        final parts = '${job['time'] ?? ''}'.split(':');
        if (parts.length >= 2) {
          final h = int.tryParse(parts[0]);
          final m = int.tryParse(parts[1]);
          if (h != null && m != null && h >= 0 && h < 24 && m >= 0 && m < 60) {
            time = TimeOfDay(hour: h, minute: m);
          }
        }
      }
    });
  }

  Future<void> _refresh() async {
    if (!mounted || serverController.text.trim().isEmpty ||
        keyController.text.trim().isEmpty) return;
    try {
      final result = await _api('GET', '/status');
      _acceptStatus(result);
    } catch (_) {
      // Keep the last successful status and let the user retry through Settings.
    }
  }

  Future<void> _start() async {
    setState(() { busy = true; error = ''; });
    try {
      await _registerToken();
      final result = await _api('POST', '/start', {
        'facility': facilityController.text.trim(),
        'date': DateFormat('yyyy-MM-dd').format(date),
        'time': '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}',
      });
      _acceptStatus(result);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _stop() async {
    setState(() { busy = true; error = ''; });
    try {
      final result = await _api('POST', '/stop');
      _acceptStatus(result);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final active = status == 'WATCHING';
    final confirmed = status == 'CONFIRMED';
    final color = confirmed ? const Color(0xFF087956) :
        active ? const Color(0xFF205B81) : const Color(0xFF7A6472);
    return Scaffold(
      appBar: AppBar(
        title: const Text('ODTÜ Spor'),
        backgroundColor: const Color(0xFF124B63),
        foregroundColor: Colors.white,
        actions: [
          IconButton(icon: const Icon(Icons.settings_outlined), tooltip: 'Sunucu ayarları',
              onPressed: () => setState(() => showingSetup = !showingSetup)),
        ],
      ),
      body: SafeArea(
        child: ListView(padding: const EdgeInsets.all(18), children: [
          Container(
            padding: const EdgeInsets.all(22),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(20),
              gradient: const LinearGradient(colors: [Color(0xFF124B63), Color(0xFF1C7991)]),
            ),
            child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(Icons.sports_tennis, color: Colors.white, size: 33),
              SizedBox(height: 14),
              Text('Rezervasyon Takip', style: TextStyle(color: Colors.white,
                  fontSize: 24, fontWeight: FontWeight.w700)),
              SizedBox(height: 6),
              Text('Uygulama kapalıyken bile takibe devam edin.',
                  style: TextStyle(color: Color(0xFFD8EAF1))),
            ]),
          ),
          const SizedBox(height: 20),
          if (!pushInitialized) ...[
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: const Color(0xFFFFF3E0), borderRadius: BorderRadius.circular(12)),
              child: Text(
                pushStartupError.isNotEmpty ? pushStartupError :
                  "Bu APK’da push bildirimleri yapılandırılmamış. İzleme durumunu görebilirsiniz, ancak uygulama kapalıyken bildirim almak için Firebase etkinleştirilmiş sürüm gerekli.",
                style: const TextStyle(color: Color(0xFF744300), fontSize: 13),
              ),
            ),
            const SizedBox(height: 16),
          ],
          if (showingSetup) ...[
            _sectionTitle('Sunucu bağlantısı'),
            TextField(controller: serverController,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(labelText: 'Backend HTTPS URL',
                    hintText: 'https://my-server.example.com')),
            const SizedBox(height: 10),
            TextField(controller: keyController, obscureText: true,
                decoration: const InputDecoration(labelText: 'Erişim anahtarı')),
            const SizedBox(height: 10),
            FilledButton(onPressed: busy ? null : _saveConnection,
                child: Text(pushInitialized ? 'Bağlan ve bildirimleri aç' : 'Sunucuya bağlan')),
            const SizedBox(height: 18),
          ],
          _sectionTitle('Takip durumu'),
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: color.withValues(alpha: 0.25)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(confirmed ? Icons.verified : active ? Icons.sync : Icons.info_outline,
                    color: color),
                const SizedBox(width: 10),
                Expanded(child: Text(status.replaceAll('_', ' '),
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 18, color: color))),
              ]),
              const SizedBox(height: 9),
              Text(lastMessage, style: const TextStyle(fontSize: 14)),
              if (lastChecked.isNotEmpty) ...[
                const SizedBox(height: 9),
                Text('Son kontrol: $lastChecked',
                    style: const TextStyle(color: Colors.black54, fontSize: 12)),
              ],
            ]),
          ),
          const SizedBox(height: 22),
          _sectionTitle('Rezervasyon tercihi'),
          TextField(controller: facilityController, enabled: !active,
              decoration: const InputDecoration(labelText: 'Spor tesisi',
                  prefixIcon: Icon(Icons.place_outlined))),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: OutlinedButton.icon(
              icon: const Icon(Icons.calendar_month_outlined),
              label: Text(DateFormat('dd MMM yyyy', 'en').format(date)),
              onPressed: active ? null : () async {
                final selected = await showDatePicker(context: context,
                    initialDate: date.isBefore(DateTime.now()) ? DateTime.now() : date,
                    firstDate: DateTime.now().subtract(const Duration(days: 1)),
                    lastDate: DateTime.now().add(const Duration(days: 365)));
                if (selected != null && mounted) setState(() => date = selected);
              },
            )),
            const SizedBox(width: 10),
            Expanded(child: OutlinedButton.icon(
              icon: const Icon(Icons.schedule),
              label: Text(time.format(context)),
              onPressed: active ? null : () async {
                final selected = await showTimePicker(context: context, initialTime: time);
                if (selected != null && mounted) setState(() => time = selected);
              },
            )),
          ]),
          const SizedBox(height: 18),
          if (error.isNotEmpty) ...[
            Text(error, style: const TextStyle(color: Color(0xFFAD2020))),
            const SizedBox(height: 12),
          ],
          FilledButton.icon(
            onPressed: busy || active || showingSetup ? null : _start,
            icon: const Icon(Icons.play_arrow),
            label: const Text('Takibi başlat'),
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: busy || !active ? null : _stop,
            icon: const Icon(Icons.stop_circle_outlined),
            label: const Text('Takibi durdur'),
            style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(52)),
          ),
          const SizedBox(height: 18),
          const Text('Kontrol aralığı: 5 dakika. Takip telefonda değil, bağlı sunucuda çalışır. '
                     'CAPTCHA ve yeniden giriş gerektiğinde bilgisayarda manuel işlem gerekir.',
              style: TextStyle(color: Colors.black54, fontSize: 12)),
        ]),
      ),
    );
  }

  Widget _sectionTitle(String value) => Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)));
}

// The Origami look. Same hex values as dashboard/src/styles/tokens.css (see dashboard/DESIGN.md).
import 'package:flutter/material.dart';

const paper = Color(0xFFF9F8F6);
const ink = Color(0xFF59534E);
const muted = Color(0xFF64605B);
const navy = Color(0xFF212E4A); // primary action and focus
const routeBlue = Color(0xFF1D6FD8); // the route line and the arrow on the map; the transit badges' blue
const routeGreen = Color(0xFF1E8E4E); // the route line while a trip is under way
const warn = Color(0xFF8A6736);
const hairline = Color(0x2459534E); // rgba(89, 83, 78, 0.14)
const edgeStrong = Color(0xFFCDCBCA); // ink at 30% over white: switch track when off
const sosRed = Color(0xFFD6001C); // an SOS: the dashboard's --sos, brighter than a hazard's red so it never reads as one

const radiusButton = BorderRadius.all(Radius.circular(6));
const radiusChip = BorderRadius.all(Radius.circular(10));
const radiusSheet = Radius.circular(18); // top corners of a bottom sheet

// ponytail: platform fonts. Flutter cannot load the dashboard's .woff2 files, so the "Lakad"
// wordmark uses Android's generic serif and everything else the platform sans (Roboto).
// Upgrade: bundle Newsreader (wordmark), Geist (text) and Archivo (controls) as TTFs under
// assets/fonts, declare them in pubspec.yaml, and point `serif` and the text theme at them.
const serif = 'serif';

ThemeData origamiTheme() {
  final base = ThemeData(
    scaffoldBackgroundColor: paper,
    colorScheme: const ColorScheme.light(
      primary: navy,
      onPrimary: paper,
      surface: Colors.white,
      onSurface: ink,
      outline: hairline,
    ),
    focusColor: const Color(0x1F212E4A), // navy at 12%
    switchTheme: SwitchThemeData(
      thumbColor: const WidgetStatePropertyAll(Colors.white),
      trackColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.selected) ? navy : edgeStrong,
      ),
      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: ink,
        minimumSize: const Size(0, 40),
        padding: const EdgeInsets.symmetric(horizontal: 14),
        shape: const RoundedRectangleBorder(borderRadius: radiusChip),
        textStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: ink,
        side: const BorderSide(color: hairline),
        minimumSize: const Size(0, 36),
        shape: const RoundedRectangleBorder(borderRadius: radiusButton),
        textStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
      ),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: radiusSheet)),
    ),
  );
  return base.copyWith(textTheme: base.textTheme.apply(bodyColor: ink, displayColor: ink));
}

/// An Origami floating chip: white, 1px hairline, radius 10, soft shadow, no blur.
class ChipCard extends StatelessWidget {
  const ChipCard({super.key, required this.child, this.padding = const EdgeInsets.all(14)});

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        borderRadius: radiusChip,
        boxShadow: [BoxShadow(color: Color(0x2959534E), blurRadius: 18, offset: Offset(0, 4))],
      ),
      // A Material, so the ink splash of a button or switch tile inside shows.
      child: Material(
        color: Colors.white,
        shape: const RoundedRectangleBorder(
          borderRadius: radiusChip,
          side: BorderSide(color: hairline),
        ),
        clipBehavior: Clip.antiAlias,
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}

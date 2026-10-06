// Where the user wants to go. The map draws it and frames it with the user's pin; the route comes next.
// The start is the live location (LocationState), so only the destination is kept here.
import 'package:flutter/foundation.dart';

import '../api/api_client.dart';

class TripState extends ChangeNotifier {
  Place? destination;

  void setDestination(Place? place) {
    destination = place;
    notifyListeners();
  }

  void clear() => setDestination(null);
}

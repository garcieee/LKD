// What the hazard is: one chip per category the server takes. A report needs exactly one.
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../theme.dart';

class CategoryPicker extends StatelessWidget {
  const CategoryPicker({super.key, required this.value, required this.onChanged});

  final String? value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final MapEntry(key: id, value: label) in categoryLabels.entries)
          ChoiceChip(
            label: Text(label),
            selected: id == value,
            onSelected: (_) => onChanged(id),
            showCheckmark: false,
            selectedColor: navy,
            backgroundColor: Colors.white,
            side: BorderSide(color: id == value ? navy : hairline),
            shape: const RoundedRectangleBorder(borderRadius: radiusButton),
            labelStyle: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: id == value ? paper : ink,
            ),
          ),
      ],
    );
  }
}

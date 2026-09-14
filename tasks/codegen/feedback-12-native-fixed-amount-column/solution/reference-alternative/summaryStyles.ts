import { StyleSheet } from 'react-native';

export const styles = StyleSheet.create({
  screen: { paddingHorizontal: 16 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  cell: { flexGrow: 0 },
  description: { flexGrow: 1, flexShrink: 1, flexBasis: 0, minWidth: 0 },
  amount: { width: 112, flexBasis: 112, flexGrow: 0, flexShrink: 0 },
  visibility: { width: 24, height: 24, flexShrink: 0, alignItems: 'center', justifyContent: 'center' },
  label: { fontSize: 14, lineHeight: 20 },
  value: { fontSize: 16, lineHeight: 22 },
});

import { StyleSheet } from 'react-native';

export const styles = StyleSheet.create({
  screen: { paddingHorizontal: 16 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  cell: { flex: 1 },
  description: { flexBasis: 'auto' },
  amount: { width: 112, flexGrow: 0, flexShrink: 0, flexBasis: 'auto' },
  visibility: { width: 24, height: 24, flexShrink: 0, alignItems: 'center', justifyContent: 'center' },
  label: { fontSize: 14, lineHeight: 20 },
  value: { fontSize: 16, lineHeight: 22 },
});

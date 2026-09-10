Wire up the Choose from Library button to expo-image-picker. Launch the picker only from the button press, offer images only, show the selected image in the preview, and keep a stable empty state when the user cancels — cancellation must never crash.

Work in `/app`. Modify the existing files and add any files required to complete the task.

Preserve the existing `testID` values on their corresponding interactive controls and displayed results; native checks use these identifiers.

Native verification contract: the harness supplies Expo 56.0.18, React 19.2.3, React Native 0.85.3, and expo-image-picker 56.0.25. Keep App.tsx as the entry point. Dependency and native app configuration changes are outside this task.

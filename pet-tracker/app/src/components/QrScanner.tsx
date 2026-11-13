/**
 * Full-screen camera that reads the QR code on a tracker's label. Other QR
 * codes are ignored with a short hint, so pointing at the wrong code is
 * harmless.
 */
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import { useRef, useState } from 'react';
import { Linking, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { parseClaimQr, type ClaimLabel } from '../claim';
import { fonts, radius, space } from '../theme';
import { Button } from './ui';

export function QrScanner({ visible, onClose, onScanned }: { visible: boolean; onClose: () => void; onScanned: (label: ClaimLabel) => void }) {
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      {visible && <Scanner onClose={onClose} onScanned={onScanned} />}
    </Modal>
  );
}

function Scanner({ onClose, onScanned }: { onClose: () => void; onScanned: (label: ClaimLabel) => void }) {
  const insets = useSafeAreaInsets();
  const [permission, requestPermission] = useCameraPermissions();
  const [torch, setTorch] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const done = useRef(false);
  const lastWrong = useRef('');

  const onBarcode = ({ data }: BarcodeScanningResult) => {
    if (done.current) return;
    const label = parseClaimQr(data);
    if (label) {
      done.current = true;
      onScanned(label);
      return;
    }
    if (data !== lastWrong.current) {
      lastWrong.current = data;
      setHint("That's not a Cat Tracker label. Look for the QR code on the collar's label or box.");
    }
  };

  const header = (
    <View style={[styles.header, { paddingTop: insets.top + space.sm }]}>
      <Pressable accessibilityRole="button" accessibilityLabel="Close" onPress={onClose} hitSlop={12} style={styles.round}>
        <Ionicons name="close" size={24} color="#fff" />
      </Pressable>
      <Text style={styles.title}>Scan the label</Text>
      {permission?.granted ? (
        <Pressable
          accessibilityRole="switch"
          accessibilityLabel="Flashlight"
          accessibilityState={{ checked: torch }}
          onPress={() => setTorch((v) => !v)}
          hitSlop={12}
          style={styles.round}
        >
          <Ionicons name={torch ? 'flashlight' : 'flashlight-outline'} size={22} color="#fff" />
        </Pressable>
      ) : (
        <View style={styles.round} />
      )}
    </View>
  );

  if (!permission) return <View style={styles.screen}>{header}</View>;

  if (!permission.granted) {
    return (
      <View style={styles.screen}>
        {header}
        <View style={styles.center}>
          <Ionicons name="camera-outline" size={40} color="#fff" />
          <Text style={styles.text}>
            The camera reads the QR code on your collar's label, so you don't have to type the code.
          </Text>
          {permission.canAskAgain ? (
            <Button title="Allow camera" icon="camera" onPress={() => void requestPermission()} />
          ) : (
            <Button title="Open phone settings" icon="settings-outline" onPress={() => void Linking.openSettings().catch(() => undefined)} />
          )}
          <Button title="Type the code instead" variant="ghost" textColor="#fff" onPress={onClose} />
        </View>
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        enableTorch={torch}
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={onBarcode}
      />
      {header}
      <View style={styles.center} pointerEvents="none">
        <View style={styles.frame} />
        <Text style={styles.text}>Point the camera at the QR code on the collar's label or box.</Text>
        {hint && (
          <View style={styles.hint}>
            <Text style={{ color: '#fff', textAlign: 'center' }}>{hint}</Text>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#0B0D12' },
  header: {
    position: 'absolute', top: 0, left: 0, right: 0, zIndex: 2, flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between', paddingHorizontal: space.lg,
  },
  round: { width: 44, height: 44, borderRadius: 22, backgroundColor: 'rgba(0,0,0,0.45)', alignItems: 'center', justifyContent: 'center' },
  title: { color: '#fff', fontFamily: fonts.display, fontSize: 18 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.lg, padding: space.xl },
  frame: { width: 240, height: 240, borderRadius: radius.lg, borderWidth: 3, borderColor: 'rgba(255,255,255,0.9)' },
  text: { color: '#fff', textAlign: 'center', fontSize: 16, lineHeight: 22, maxWidth: 300 },
  hint: { backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: radius.md, padding: space.md, maxWidth: 320 },
});

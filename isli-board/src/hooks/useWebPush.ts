import { useState, useEffect, useCallback } from 'react';

const VAPID_PUBLIC_KEY_URL = '/api/v1/notifications/web-push/public-key';
const SUBSCRIBE_URL = '/api/v1/notifications/web-push/subscribe';
const UNSUBSCRIBE_URL = '/api/v1/notifications/web-push/unsubscribe';

function urlBase64ToUint8Array(base64String: string) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export function useWebPush(userId: string | null) {
  const [isSupported, setIsSupported] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission>('default');
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);
  const [isIOS, setIsIOS] = useState(false);

  useEffect(() => {
    const supported = 'serviceWorker' in navigator && 'PushManager' in window;
    setIsSupported(supported);
    setPermission(Notification.permission);
    setIsStandalone(window.matchMedia('(display-mode: standalone)').matches);
    setIsIOS(/iPad|iPhone|iPod/.test(navigator.userAgent));

    if (supported) {
      navigator.serviceWorker.ready.then((registration) => {
        registration.pushManager.getSubscription().then((subscription) => {
          setIsSubscribed(!!subscription);
        });
      });
    }
  }, []);

  const subscribe = useCallback(async () => {
    if (!userId || !isSupported) return;

    try {
      // 1. Get VAPID public key
      const keyResp = await fetch(VAPID_PUBLIC_KEY_URL);
      if (!keyResp.ok) throw new Error('Failed to fetch VAPID key');
      const { public_key } = await keyResp.json();

      // 2. Request permission
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== 'granted') return;

      // 3. Subscribe via PushManager
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      });

      // 4. Send to backend
      const { endpoint, keys } = subscription.toJSON();
      if (!endpoint || !keys) throw new Error('Invalid subscription object');

      const subResp = await fetch(`${SUBSCRIBE_URL}?user_id=${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint,
          p256dh: keys.p256dh,
          auth: keys.auth,
        }),
      });

      if (!subResp.ok) throw new Error('Failed to register subscription with backend');
      setIsSubscribed(true);
    } catch (err) {
      console.error('Web Push subscription failed:', err);
      throw err;
    }
  }, [userId, isSupported]);

  const unsubscribe = useCallback(async () => {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        // 1. Unsubscribe on backend
        await fetch(`${UNSUBSCRIBE_URL}?endpoint=${encodeURIComponent(subscription.endpoint)}`, {
          method: 'DELETE',
        });
        // 2. Unsubscribe locally
        await subscription.unsubscribe();
      }
      setIsSubscribed(false);
    } catch (err) {
      console.error('Web Push unsubscription failed:', err);
    }
  }, []);

  return {
    isSupported,
    permission,
    isSubscribed,
    isStandalone,
    isIOS,
    subscribe,
    unsubscribe,
  };
}

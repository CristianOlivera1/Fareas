import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';

interface SessionDescription {
  type: string;
  sdp: string;
}

const ICE_GATHER_TIMEOUT_MS = 2000;
const DISCONNECT_GRACE_MS = 4000;

@Injectable()
export class CameraWebrtc {
  private readonly http = inject(HttpClient);
  private peer: RTCPeerConnection | null = null;
  private graceTimer: ReturnType<typeof setTimeout> | null = null;

  readonly supported = typeof RTCPeerConnection !== 'undefined';
  readonly lost = signal(false);

  async start(video: HTMLVideoElement, roomId: number): Promise<boolean> {
    this.stop();
    if (!this.supported) return false;
    this.lost.set(false);
    const peer = new RTCPeerConnection({ iceServers: [] });
    this.peer = peer;
    peer.addTransceiver('video', { direction: 'recvonly' });
    peer.ontrack = (event) => {
      video.srcObject = event.streams[0] ?? new MediaStream([event.track]);
    };
    peer.onconnectionstatechange = () => this.watch(peer);
    try {
      await peer.setLocalDescription(await peer.createOffer());
      await this.iceGathered(peer);
      const local = peer.localDescription;
      if (!local) return this.fail(peer);
      const answer = await firstValueFrom(
        this.http.post<SessionDescription>(`${environment.apiUrl}/dashboard/camera/${roomId}/webrtc`, {
          type: 'offer',
          sdp: local.sdp,
        }),
      );
      if (this.peer !== peer) return false;
      await peer.setRemoteDescription({ type: 'answer', sdp: answer.sdp });
      await video.play().catch(() => undefined);
      return true;
    } catch {
      return this.fail(peer);
    }
  }

  stop(): void {
    if (this.graceTimer) clearTimeout(this.graceTimer);
    this.graceTimer = null;
    const peer = this.peer;
    this.peer = null;
    if (peer) {
      peer.onconnectionstatechange = null;
      peer.ontrack = null;
      peer.close();
    }
  }

  private fail(peer: RTCPeerConnection): false {
    if (this.peer === peer) this.stop();
    return false;
  }

  private watch(peer: RTCPeerConnection): void {
    if (this.peer !== peer) return;
    if (this.graceTimer) clearTimeout(this.graceTimer);
    this.graceTimer = null;
    if (peer.connectionState === 'failed' || peer.connectionState === 'closed') {
      this.lost.set(true);
    } else if (peer.connectionState === 'disconnected') {
      this.graceTimer = setTimeout(() => this.lost.set(true), DISCONNECT_GRACE_MS);
    }
  }

  private iceGathered(peer: RTCPeerConnection): Promise<void> {
    if (peer.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise((resolve) => {
      const finish = () => {
        peer.removeEventListener('icegatheringstatechange', onChange);
        clearTimeout(timer);
        resolve();
      };
      const onChange = () => {
        if (peer.iceGatheringState === 'complete') finish();
      };
      const timer = setTimeout(finish, ICE_GATHER_TIMEOUT_MS);
      peer.addEventListener('icegatheringstatechange', onChange);
    });
  }
}

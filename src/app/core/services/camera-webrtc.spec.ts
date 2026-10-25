import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';

import { CameraWebrtc } from './camera-webrtc';

describe('CameraWebrtc', () => {
  let service: CameraWebrtc;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), CameraWebrtc] });
    service = TestBed.inject(CameraWebrtc);
  });

  it('reports unsupported browsers so the page can fall back to MJPEG', async () => {
    const video = document.createElement('video');

    expect(service.supported).toBe(false);
    expect(await service.start(video, 1)).toBe(false);
    expect(service.lost()).toBe(false);
  });
});

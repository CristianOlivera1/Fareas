import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AuthService } from '../../../../core/services/auth/auth';
import { CameraWebrtc } from '../../../../core/services/camera-webrtc';
import { LiveFeed } from '../../../../core/services/live-feed';
import { ActivityFeed } from './activity-feed';

const API = 'http://localhost:8000/api/v1';

describe('ActivityFeed', () => {
  let fixture: ComponentFixture<ActivityFeed>;
  let httpMock: HttpTestingController;
  let connect: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    localStorage.clear();
    connect = vi.fn();
    TestBed.overrideComponent(ActivityFeed, {
      set: {
        providers: [
          CameraWebrtc,
          { provide: LiveFeed, useValue: { connect, close: vi.fn(), status: () => 'idle', latest: () => null } },
        ],
      },
    });
    await TestBed.configureTestingModule({
      imports: [ActivityFeed],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { accessToken: () => 'token-de-prueba-123' } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ActivityFeed);
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url === `${API}/rooms`).flush({ items: [], total: 0, page: 1, page_size: 100 });
  });

  afterEach(() => httpMock.verify());

  function flushCameras(liveRoomId: number | null): void {
    httpMock.expectOne((req) => req.url === `${API}/settings`).flush({ live_room_id: liveRoomId });
    httpMock.expectOne((req) => req.url === `${API}/devices`).flush({
      items: [
        { id: 1, room_id: 7, room_code: 'LAB 305', device_type: 'camara', is_active: true },
        { id: 2, room_id: 9, room_code: 'LAB 306', device_type: 'camara', is_active: true },
        { id: 3, room_id: 11, room_code: 'LAB 401', device_type: 'camara', is_active: false },
      ],
      total: 3,
      page: 1,
      page_size: 100,
    });
    fixture.detectChanges();
  }

  it('connects to the room configured in Parámetros', () => {
    flushCameras(9);

    expect(connect).toHaveBeenLastCalledWith(9);
    expect(fixture.componentInstance.roomLabel()).toBe('LAB 306');
  });

  it('falls back to the first active camera when nothing is configured', () => {
    flushCameras(null);

    expect(connect).toHaveBeenLastCalledWith(7);
  });

  it('ignores a configured room whose camera is inactive', () => {
    flushCameras(11);

    expect(connect).toHaveBeenLastCalledWith(7);
  });

  it('does not connect when there are no active cameras', () => {
    httpMock.expectOne((req) => req.url === `${API}/settings`).flush({ live_room_id: null });
    httpMock.expectOne((req) => req.url === `${API}/devices`).flush({ items: [], total: 0, page: 1, page_size: 100 });
    fixture.detectChanges();

    expect(connect).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('No hay cámaras activas');
  });

  it('shows the live stream of the configured room', () => {
    flushCameras(9);
    fixture.detectChanges();

    const image = fixture.nativeElement.querySelector('img') as HTMLImageElement | null;
    expect(fixture.componentInstance.roomLabel()).toBe('LAB 306');
    expect(fixture.componentInstance.streamUrl()).toContain('/dashboard/camera/9/mjpeg?access_token=');
    expect(image?.getAttribute('src')).toContain('/dashboard/camera/9/mjpeg');
  });
});

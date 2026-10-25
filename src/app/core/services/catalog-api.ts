import { Injectable } from '@angular/core';
import { apiUrl, BaseApi, Page, ListParams } from '../api/api-url';
import { Device, DeviceType, Person, Room } from '../models/catalog';
import {
  StudentImportConfirmIn,
  StudentImportPreview,
  StudentImportResult,
} from '../models/imports';

@Injectable({ providedIn: 'root' })
export class CatalogApi extends BaseApi {
  rooms(params?: ListParams) {
    return this.get<Page<Room>>('/rooms', params);
  }
  createRoom(body: { code: string; name?: string | null; building?: string | null }) {
    return this.post<Room>('/rooms', body);
  }
  updateRoom(id: number, body: { name?: string | null; building?: string | null; is_active?: boolean }) {
    return this.patch<Room>(`/rooms/${id}`, body);
  }

  devices(params?: ListParams & { room_id?: number; device_type?: DeviceType }) {
    return this.get<Page<Device>>('/devices', params);
  }
  deviceStatus() {
    return this.get<Device[]>('/devices/status');
  }
  createDevice(body: {
    room_id: number;
    device_type: DeviceType;
    device_key: string;
    name?: string | null;
    rtsp_url?: string | null;
  }) {
    return this.post<Device>('/devices', body);
  }
  updateDevice(
    id: number,
    body: { name?: string | null; rtsp_url?: string | null; ip_address?: string | null; is_active?: boolean },
  ) {
    return this.patch<Device>(`/devices/${id}`, body);
  }

  teachers(params?: ListParams) {
    return this.get<Page<Person>>('/teachers', params);
  }
  createTeacher(body: { full_name: string; email: string; dni: string; whatsapp?: string | null }) {
    return this.post<Person>('/teachers', body);
  }
  students(params?: ListParams & { semester?: number }) {
    return this.get<Page<Person>>('/students', params);
  }
  createStudent(body: {
    full_name: string;
    email: string;
    dni: string;
    code: string;
    semester: number;
    whatsapp?: string | null;
  }) {
    return this.post<Person>('/students', body);
  }
  account(id: number) {
    return this.get<Person>(`/accounts/${id}`);
  }
  updateAccount(
    id: number,
    body: { full_name?: string; whatsapp?: string | null; is_active?: boolean; semester?: number },
  ) {
    return this.patch<Person>(`/accounts/${id}`, body);
  }
  resendCredentials(id: number) {
    return this.post<{ message: string }>(`/accounts/${id}/send-temp-password`);
  }

  importStudentsPreview(file: File, defaultSemester: number) {
    const body = new FormData();
    body.append('file', file);
    body.append('default_semester', String(defaultSemester));
    return this.http.post<StudentImportPreview>(apiUrl('/students/import-preview'), body);
  }
  importStudentsConfirm(body: StudentImportConfirmIn) {
    return this.post<StudentImportResult>('/students/import-confirm', body);
  }
}

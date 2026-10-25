import { containedFrame, easeBox, toCanvasBox } from './face-box';

describe('face-box', () => {
  it('letterboxes a 16:9 video inside a taller container', () => {
    const frame = containedFrame(400, 400, 1600, 900);

    expect(frame.width).toBe(400);
    expect(frame.height).toBe(225);
    expect(frame.x).toBe(0);
    expect(frame.y).toBe(87.5);
  });

  it('fills the container while the video size is unknown', () => {
    expect(containedFrame(300, 200, 0, 0)).toEqual({ x: 0, y: 0, width: 300, height: 200 });
  });

  it('maps normalized boxes into canvas pixels', () => {
    const frame = containedFrame(400, 400, 1600, 900);

    expect(toCanvasBox([0.5, 0.5, 1, 1], frame)).toEqual([200, 200, 400, 312.5]);
  });

  it('eases toward the target box', () => {
    expect(easeBox([0, 0, 10, 10], [10, 10, 20, 20], 0.5)).toEqual([5, 5, 15, 15]);
  });
});

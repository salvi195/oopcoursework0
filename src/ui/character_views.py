from __future__ import annotations

import math

import pygame


class CharacterViewsMixin:
    """Vector-drawn opponent portraits (pig, wolf, bull, bunny) and shared decorations."""

    def _draw_pig_character(
        self,
        x: int,
        y: int,
        active: bool,
        claimant: bool,
        hand_size: int,
    ) -> None:
        outline = (39, 21, 18)
        fur = (206, 143, 116)
        fur_light = (232, 184, 154)
        fur_shadow = (122, 70, 58)
        shirt = (214, 208, 196)
        shirt_shadow = (176, 166, 152)
        shadow = pygame.Surface((300, 300), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 34), shadow.get_rect())
        self.screen.blit(shadow, (x - 150, y + 10))
        body = pygame.Rect(x - 124, y + 88, 176, 132)
        shoulders = [
            (x - 112, y + 198),
            (x - 102, y + 120),
            (x - 60, y + 90),
            (x - 8, y + 88),
            (x + 30, y + 106),
            (x + 46, y + 198),
        ]
        self._draw_halo((x + 8, y + 18), 52, active)
        pygame.draw.ellipse(self.screen, fur, body)
        pygame.draw.polygon(self.screen, fur, shoulders)
        tank = [(x - 104, y + 192), (x - 78, y + 104), (x - 22, y + 96), (x + 38, y + 196)]
        pygame.draw.polygon(self.screen, shirt, tank)
        pygame.draw.polygon(
            self.screen,
            shirt_shadow,
            [(x - 36, y + 132), (x - 14, y + 100), (x + 6, y + 104), (x - 14, y + 154)],
        )
        self._blit_soft_ellipse(pygame.Rect(body.x + 18, body.y + 12, 72, 50), (255, 230, 206, 34))
        self._blit_soft_ellipse(pygame.Rect(body.x + 48, body.y + 70, 88, 42), (94, 52, 44, 24))
        neck = [(x - 18, y + 88), (x + 18, y + 88), (x + 28, y + 112), (x - 28, y + 112)]
        pygame.draw.polygon(self.screen, fur, neck)
        pygame.draw.arc(self.screen, outline, body, 0.34, math.pi - 0.34, 3)
        pygame.draw.lines(self.screen, outline, False, [shoulders[0], shoulders[1], shoulders[2]], 3)
        pygame.draw.lines(
            self.screen,
            outline,
            False,
            [shoulders[3], shoulders[4], shoulders[5], shoulders[0]],
            3,
        )
        pygame.draw.polygon(self.screen, outline, tank, 3)
        head = pygame.Rect(x - 30, y + 12, 94, 88)
        pygame.draw.ellipse(self.screen, fur, head)
        self._blit_soft_ellipse(pygame.Rect(head.x + 12, head.y + 10, 48, 24), (255, 224, 196, 30))
        self._blit_soft_ellipse(pygame.Rect(head.x + 20, head.y + 36, 58, 36), (118, 70, 58, 28))
        self._blit_soft_ellipse(pygame.Rect(head.x + 14, head.y + 56, 62, 18), (246, 214, 190, 20))
        ear_left = [(x - 16, y + 26), (x + 2, y - 6), (x + 16, y + 30)]
        ear_right = [(x + 14, y + 24), (x + 34, y - 2), (x + 48, y + 32)]
        pygame.draw.polygon(self.screen, fur, ear_left)
        pygame.draw.polygon(self.screen, fur, ear_right)
        pygame.draw.polygon(self.screen, fur_light, [(x - 8, y + 72), (x + 20, y + 62), (x + 46, y + 72), (x + 24, y + 84)])
        snout = pygame.Rect(x + 2, y + 48, 44, 26)
        pygame.draw.ellipse(self.screen, (236, 183, 160), snout)
        pygame.draw.circle(self.screen, (154, 86, 79), (x + 18, y + 60), 3)
        pygame.draw.circle(self.screen, (154, 86, 79), (x + 30, y + 60), 3)
        pygame.draw.ellipse(self.screen, (242, 241, 236), pygame.Rect(x - 6, y + 36, 13, 10))
        pygame.draw.ellipse(self.screen, (242, 241, 236), pygame.Rect(x + 19, y + 36, 13, 10))
        pygame.draw.circle(self.screen, outline, (x + 1, y + 41), 3)
        pygame.draw.circle(self.screen, outline, (x + 26, y + 41), 3)
        pygame.draw.arc(self.screen, outline, pygame.Rect(x + 14, y + 68, 14, 8), 0.3, 2.85, 2)
        pygame.draw.arc(self.screen, fur_shadow, pygame.Rect(x - 2, y + 32, 18, 12), 3.6, 5.8, 2)
        pygame.draw.arc(self.screen, fur_shadow, pygame.Rect(x + 20, y + 32, 18, 12), 3.6, 5.8, 2)
        arm = [(x - 10, y + 136), (x + 56, y + 146), (x + 138, y + 154), (x + 132, y + 184), (x + 46, y + 176), (x - 14, y + 160)]
        pygame.draw.polygon(self.screen, fur, arm)
        hand = pygame.Rect(x + 126, y + 148, 32, 22)
        pygame.draw.ellipse(self.screen, fur, hand)
        self._draw_card_fan((x + 164, y + 148), min(hand_size, 4), 18, 50, False, claimant)
        pygame.draw.ellipse(self.screen, outline, head, 3)
        pygame.draw.polygon(self.screen, outline, ear_left, 3)
        pygame.draw.polygon(self.screen, outline, ear_right, 3)
        pygame.draw.ellipse(self.screen, outline, snout, 2)

    def _draw_wolf_character(
        self,
        x: int,
        y: int,
        active: bool,
        claimant: bool,
        hand_size: int,
    ) -> None:
        outline = (26, 29, 31)
        fur = (122, 128, 136)
        fur_dark = (76, 82, 92)
        shirt = (214, 214, 210)
        suit = (76, 92, 78)
        self._draw_halo((x - 10, y - 54), 58, active)
        body = pygame.Rect(x - 88, y + 34, 176, 132)
        shoulders = [
            (x - 82, y + 142),
            (x - 66, y + 68),
            (x - 28, y + 38),
            (x + 28, y + 38),
            (x + 68, y + 70),
            (x + 84, y + 142),
        ]
        pygame.draw.ellipse(self.screen, suit, body)
        pygame.draw.polygon(self.screen, suit, shoulders)
        self._blit_soft_ellipse(pygame.Rect(body.x + 20, body.y + 10, 70, 42), (214, 224, 218, 20))
        self._blit_soft_ellipse(pygame.Rect(body.x + 36, body.y + 56, 112, 58), (18, 20, 24, 30))
        chest = [(x - 34, y + 126), (x - 18, y + 42), (x + 18, y + 42), (x + 34, y + 126)]
        pygame.draw.polygon(self.screen, shirt, chest)
        tie = [(x - 6, y + 46), (x + 6, y + 46), (x + 12, y + 100), (x - 12, y + 100)]
        pygame.draw.polygon(self.screen, (129, 34, 34), tie)
        head = pygame.Rect(x - 50, y - 74, 100, 112)
        pygame.draw.ellipse(self.screen, fur, head)
        self._blit_soft_ellipse(pygame.Rect(head.x + 14, head.y + 8, 54, 42), (236, 242, 245, 34))
        self._blit_soft_ellipse(pygame.Rect(head.x + 26, head.y + 46, 52, 40), (32, 36, 42, 34))
        ear_left = [(x - 34, y - 56), (x - 18, y - 96), (x + 2, y - 44)]
        ear_right = [(x + 18, y - 44), (x + 34, y - 96), (x + 52, y - 56)]
        pygame.draw.polygon(self.screen, fur_dark, ear_left)
        pygame.draw.polygon(self.screen, fur_dark, ear_right)
        muzzle = [(x - 20, y - 6), (x + 22, y - 2), (x + 12, y + 28), (x - 10, y + 26)]
        pygame.draw.polygon(self.screen, (198, 203, 208), muzzle)
        pygame.draw.circle(self.screen, (240, 240, 236), (x - 16, y - 18), 8)
        pygame.draw.circle(self.screen, (240, 240, 236), (x + 18, y - 18), 8)
        pygame.draw.circle(self.screen, outline, (x - 14, y - 18), 4)
        pygame.draw.circle(self.screen, outline, (x + 16, y - 18), 4)
        pygame.draw.polygon(self.screen, outline, [(x + 4, y + 2), (x + 16, y + 8), (x + 8, y + 18)])
        arm = [(x + 18, y + 96), (x + 72, y + 118), (x + 92, y + 144), (x + 68, y + 152), (x + 6, y + 118)]
        pygame.draw.polygon(self.screen, fur, arm)
        self._draw_card_fan((x + 98, y + 132), min(hand_size, 3), 18, 18, False, claimant)
        pygame.draw.ellipse(self.screen, outline, body, 4)
        pygame.draw.lines(self.screen, outline, False, [shoulders[0], shoulders[1], shoulders[2]], 4)
        pygame.draw.lines(self.screen, outline, False, [shoulders[3], shoulders[4], shoulders[5], shoulders[0]], 4)
        pygame.draw.polygon(self.screen, outline, chest, 3)
        pygame.draw.ellipse(self.screen, outline, head, 4)
        pygame.draw.polygon(self.screen, outline, ear_left, 4)
        pygame.draw.polygon(self.screen, outline, ear_right, 4)
        pygame.draw.polygon(self.screen, outline, muzzle, 3)

    def _draw_bull_character(
        self,
        x: int,
        y: int,
        active: bool,
        claimant: bool,
        hand_size: int,
    ) -> None:
        outline = (38, 22, 16)
        fur = (151, 99, 61)
        muzzle = (194, 150, 113)
        shirt = (73, 76, 82)
        horn = (228, 210, 188)
        self._draw_halo((x, y - 56), 92, active or claimant)
        body = pygame.Rect(x - 128, y + 30, 256, 160)
        shoulders = [
            (x - 122, y + 148),
            (x - 92, y + 66),
            (x - 42, y + 28),
            (x + 42, y + 28),
            (x + 92, y + 66),
            (x + 124, y + 148),
        ]
        pygame.draw.ellipse(self.screen, shirt, body)
        pygame.draw.polygon(self.screen, shirt, shoulders)
        self._blit_soft_ellipse(pygame.Rect(body.x + 36, body.y + 10, 96, 48), (214, 220, 228, 18))
        self._blit_soft_ellipse(pygame.Rect(body.x + 70, body.y + 72, 142, 60), (18, 20, 24, 34))
        head = pygame.Rect(x - 86, y - 104, 172, 164)
        pygame.draw.ellipse(self.screen, fur, head)
        self._blit_soft_ellipse(pygame.Rect(head.x + 28, head.y + 14, 78, 48), (255, 230, 198, 30))
        self._blit_soft_ellipse(pygame.Rect(head.x + 60, head.y + 66, 84, 52), (82, 50, 36, 32))
        pygame.draw.polygon(self.screen, horn, [(x - 66, y - 62), (x - 118, y - 102), (x - 82, y - 54)])
        pygame.draw.polygon(self.screen, horn, [(x + 66, y - 62), (x + 118, y - 102), (x + 82, y - 54)])
        muzzle_rect = pygame.Rect(x - 44, y - 6, 88, 56)
        pygame.draw.ellipse(self.screen, muzzle, muzzle_rect)
        pygame.draw.circle(self.screen, (86, 56, 42), (x - 16, y + 20), 7)
        pygame.draw.circle(self.screen, (86, 56, 42), (x + 16, y + 20), 7)
        pygame.draw.circle(self.screen, (244, 244, 240), (x - 34, y - 18), 11)
        pygame.draw.circle(self.screen, (244, 244, 240), (x + 34, y - 18), 11)
        pygame.draw.circle(self.screen, outline, (x - 32, y - 18), 5)
        pygame.draw.circle(self.screen, outline, (x + 32, y - 18), 5)
        pygame.draw.arc(self.screen, (204, 183, 120), pygame.Rect(x - 16, y + 20, 32, 24), 0.15, 3.0, 4)
        arm_left = [(x - 70, y + 108), (x - 126, y + 152), (x - 138, y + 198), (x - 108, y + 198), (x - 58, y + 148)]
        arm_right = [(x + 70, y + 108), (x + 126, y + 150), (x + 148, y + 194), (x + 118, y + 198), (x + 58, y + 148)]
        pygame.draw.polygon(self.screen, fur, arm_left)
        pygame.draw.polygon(self.screen, fur, arm_right)
        pygame.draw.ellipse(self.screen, fur, pygame.Rect(x - 142, y + 188, 36, 24))
        pygame.draw.ellipse(self.screen, fur, pygame.Rect(x + 118, y + 184, 36, 26))
        self._draw_card_fan((x + 170, y + 172), min(hand_size, 4), 16, -16, True, claimant)
        pygame.draw.ellipse(self.screen, outline, body, 4)
        pygame.draw.lines(self.screen, outline, False, [shoulders[0], shoulders[1], shoulders[2]], 4)
        pygame.draw.lines(self.screen, outline, False, [shoulders[3], shoulders[4], shoulders[5], shoulders[0]], 4)
        pygame.draw.ellipse(self.screen, outline, head, 4)
        pygame.draw.polygon(self.screen, outline, arm_left, 4)
        pygame.draw.polygon(self.screen, outline, arm_right, 4)
        pygame.draw.ellipse(self.screen, outline, muzzle_rect, 3)

    def _draw_bunny_character(
        self,
        x: int,
        y: int,
        active: bool,
        claimant: bool,
        hand_size: int,
    ) -> None:
        outline = (43, 22, 18)
        fur = (196, 116, 72)
        fur_dark = (118, 62, 46)
        fur_light = (234, 196, 162)
        top = (62, 27, 31)
        self._draw_halo((x - 18, y + 10), 56, active)
        body = pygame.Rect(x - 94, y + 88, 174, 128)
        shoulders = [
            (x - 90, y + 194),
            (x - 76, y + 120),
            (x - 36, y + 90),
            (x + 12, y + 88),
            (x + 54, y + 104),
            (x + 74, y + 194),
        ]
        pygame.draw.ellipse(self.screen, fur, body)
        pygame.draw.polygon(self.screen, fur, shoulders)
        blouse = [(x - 44, y + 192), (x - 8, y + 100), (x + 42, y + 94), (x + 76, y + 194)]
        pygame.draw.polygon(self.screen, top, blouse)
        self._blit_soft_ellipse(pygame.Rect(body.x + 18, body.y + 12, 68, 38), (248, 214, 182, 24))
        self._blit_soft_ellipse(pygame.Rect(body.x + 44, body.y + 64, 86, 46), (74, 34, 30, 32))
        neck = [(x - 18, y + 88), (x + 18, y + 88), (x + 30, y + 110), (x - 26, y + 112)]
        pygame.draw.polygon(self.screen, fur, neck)
        pygame.draw.arc(self.screen, outline, body, 0.32, math.pi - 0.32, 3)
        pygame.draw.lines(self.screen, outline, False, [shoulders[0], shoulders[1], shoulders[2]], 3)
        pygame.draw.lines(
            self.screen,
            outline,
            False,
            [shoulders[3], shoulders[4], shoulders[5], shoulders[0]],
            3,
        )
        pygame.draw.polygon(self.screen, outline, blouse, 3)
        head = pygame.Rect(x - 36, y + 22, 88, 80)
        pygame.draw.ellipse(self.screen, fur, head)
        self._blit_soft_ellipse(pygame.Rect(head.x + 10, head.y + 8, 42, 18), (255, 230, 194, 26))
        self._blit_soft_ellipse(pygame.Rect(head.x + 22, head.y + 32, 42, 26), (108, 58, 44, 26))
        ear_left = [(x - 24, y + 32), (x - 8, y - 2), (x + 8, y + 34)]
        ear_right = [(x + 4, y + 34), (x + 24, y + 2), (x + 38, y + 38)]
        pygame.draw.polygon(self.screen, fur, ear_left)
        pygame.draw.polygon(self.screen, fur, ear_right)
        cheek = [(x - 18, y + 70), (x - 8, y + 50), (x + 8, y + 46), (x + 26, y + 52), (x + 28, y + 70), (x + 4, y + 82)]
        pygame.draw.polygon(self.screen, fur_light, cheek)
        muzzle = [(x - 8, y + 56), (x + 14, y + 54), (x + 22, y + 64), (x + 2, y + 74), (x - 10, y + 66)]
        pygame.draw.polygon(self.screen, fur_light, muzzle)
        pygame.draw.ellipse(self.screen, (244, 243, 238), pygame.Rect(x - 22, y + 40, 14, 8))
        pygame.draw.ellipse(self.screen, (244, 243, 238), pygame.Rect(x + 2, y + 40, 14, 8))
        pygame.draw.circle(self.screen, outline, (x - 14, y + 44), 3)
        pygame.draw.circle(self.screen, outline, (x + 10, y + 44), 3)
        pygame.draw.arc(self.screen, fur_dark, pygame.Rect(x - 24, y + 34, 20, 12), 3.7, 5.8, 2)
        pygame.draw.arc(self.screen, fur_dark, pygame.Rect(x, y + 34, 20, 12), 3.7, 5.8, 2)
        pygame.draw.polygon(self.screen, fur_dark, [(x + 2, y + 58), (x + 8, y + 64), (x + 2, y + 70)])
        pygame.draw.arc(self.screen, outline, pygame.Rect(x - 4, y + 68, 14, 7), 0.25, 2.85, 2)
        arm = [(x - 14, y + 136), (x - 84, y + 146), (x - 148, y + 142), (x - 144, y + 170), (x - 58, y + 168), (x - 6, y + 154)]
        pygame.draw.polygon(self.screen, fur, arm)
        hand = pygame.Rect(x - 148, y + 144, 30, 20)
        pygame.draw.ellipse(self.screen, fur_light, hand)
        necklace_y = y + 104
        pygame.draw.line(self.screen, (214, 193, 150), (x - 14, necklace_y), (x + 34, necklace_y), 2)
        pygame.draw.circle(self.screen, (214, 193, 150), (x + 10, necklace_y + 7), 4)
        self._draw_card_fan((x - 162, y + 144), min(hand_size, 4), 16, -50, True, claimant)
        pygame.draw.ellipse(self.screen, outline, head, 3)
        pygame.draw.polygon(self.screen, outline, ear_left, 3)
        pygame.draw.polygon(self.screen, outline, ear_right, 3)
        pygame.draw.polygon(self.screen, outline, cheek, 2)
        pygame.draw.polygon(self.screen, outline, muzzle, 2)

    def _draw_card_fan(
        self,
        center: tuple[int, int],
        count: int,
        spread: int,
        base_angle: int,
        mirrored: bool,
        highlighted: bool,
    ) -> None:
        for index in range(count):
            offset = index - (count - 1) / 2
            rect = pygame.Rect(
                int(center[0] + offset * (spread // 1.5)),
                int(center[1] - abs(offset) * 4),
                56,
                78,
            )
            angle = base_angle + int(offset * spread)
            if mirrored:
                angle *= -1
            self._draw_card_back(rect, highlighted=highlighted and index == count - 1, angle=angle)

    def _draw_halo(self, center: tuple[int, int], radius: int, enabled: bool) -> None:
        if not enabled:
            return
        halo = pygame.Surface((radius * 3, radius * 3), pygame.SRCALPHA)
        pygame.draw.circle(halo, (241, 202, 129, 32), (halo.get_width() // 2, halo.get_height() // 2), radius)
        self.screen.blit(halo, halo.get_rect(center=center))

    def _draw_tag(self, label: str, pos: tuple[int, int], color: tuple[int, int, int]) -> None:
        text = self.fonts["tiny"].render(label, True, (18, 20, 24))
        rect = text.get_rect()
        rect.topleft = pos
        badge = pygame.Rect(rect.x - 8, rect.y - 4, rect.width + 16, rect.height + 8)
        pygame.draw.rect(self.screen, color, badge, border_radius=10)
        self.screen.blit(text, rect)

/* WARNING: Unknown calling convention -- yet parameter storage is locked */

short CloseFreddiFile(undefined *file)

{
  int iVar1;
  short sVar2;
  int iVar3;
  int iVar4;
  undefined auStack_160 [16];
  short sStack_150;
  undefined1 *puStack_14e;
  undefined2 uStack_14a;
  short sStack_148;
  undefined1 uStack_146;
  short sStack_144;
  undefined4 uStack_130;
  undefined1 auStack_110 [256];

  iVar1 = LMGetFCBSPtr();
  iVar1 = *(short *)(file + 6) + iVar1;
  iVar4 = 0;
  iVar3 = *(int *)(iVar1 + 0x14);
  uStack_14a = *(undefined2 *)(iVar3 + 0x4e);
  if ((*(uint *)file >> 0x18 & 1) != 0) {
    puStack_14e = auStack_110;
    uStack_146 = 0;
    if (*(short *)(iVar3 + 8) == 0x4244) {
      uStack_130 = *(undefined4 *)(iVar1 + 0x3a);
      func_0x100066e8(puStack_14e,(byte *)(iVar1 + 0x3e),*(byte *)(iVar1 + 0x3e) + 1);
      iVar4 = 2;
    }
    else if (*(short *)(iVar3 + 8) == -0x2d29) {
      sStack_144 = 1;
      while (sVar2 = PBGetFInfoSync(auStack_160), sVar2 == 0) {
        if (*(short *)(file + 6) == sStack_148) {
          iVar4 = 1;
          break;
        }
        sStack_144 = sStack_144 + 1;
      }
    }
  }
  sStack_148 = *(short *)(file + 6);
  sVar2 = PBCloseSync(auStack_160);
  if (sVar2 == 0) {
    if (iVar4 == 1) {
      PBDeleteSync(auStack_160);
    }
    else if (iVar4 == 2) {
      PBHDeleteSync(auStack_160);
    }
    puStack_14e = (undefined1 *)0x0;
    PBFlushVolSync(auStack_160);
  }
  return sStack_150;
}

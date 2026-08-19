from pathlib import Path
import re, struct, zlib

root = Path('RFToolsBuilderPort261')
java = root / 'src/main/java/mcjty/rftoolsbuilder'
client = java / 'client'
res = root / 'src/main/resources'

# Quantum Tools 3.0.5
# - machine display name: Miner (mod name stays Quantum Tools for now)
# - aligned Miner UI
# - exact 18x18 visual frames around 16x16 card slots
# - Start/Pause/Resume + separate Stop (Stop resets progress)
# - per-entry Whitelist/Blacklist rules, blacklist always wins
# - redesigned coherent card sprites

p = java / 'BuilderBlockEntity.java'
s = p.read_text(encoding='utf-8')
if 'STATUS_PAUSED' not in s:
    s = s.replace('    public static final int STATUS_DONE = 5;\n', '    public static final int STATUS_DONE = 5;\n    public static final int STATUS_PAUSED = 6;\n', 1)
pat = re.compile(r'''    public void toggleRunning\(\) \{.*?\n    \}\n\n    public boolean hasShapeCard\(\)''', re.S)
replacement = r'''    public void primaryAction() {
        if (running) {
            running = false;
            status = STATUS_PAUSED;
            setChanged();
            syncClientState();
            return;
        }
        if (status == STATUS_PAUSED) {
            running = true;
            status = STATUS_RUNNING;
            setChanged();
            syncClientState();
            return;
        }
        if (status == STATUS_DONE || cursor >= volume()) resetProgress();
        running = true;
        status = STATUS_RUNNING;
        setChanged();
        syncClientState();
    }

    public void stopWork() {
        running = false;
        cursor = 0L;
        scanChunkIndex = 0;
        cursorInChunk = 0L;
        status = STATUS_IDLE;
        setChanged();
        syncClientState();
    }

    public void toggleRunning() { primaryAction(); }

    public boolean hasShapeCard()'''
s, n = pat.subn(replacement, s, count=1)
if n != 1: raise SystemExit('BuilderBlockEntity toggleRunning block not found')
p.write_text(s, encoding='utf-8')

(java / 'QuarryCardItem.java').write_text(r'''package mcjty.rftoolsbuilder;

import net.minecraft.ChatFormatting;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.TagKey;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.SimpleMenuProvider;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import net.minecraft.world.item.component.CustomData;
import net.minecraft.world.item.component.TooltipDisplay;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class QuarryCardItem extends Item {
    public static final int MAX_FILTER_ENTRIES = 18;
    private static final String P = "QuantumFilter";
    private static final String LEGACY_BLACK = P + "Blacklist";
    private static final String DAMAGE = P + "Damage";
    private static final String NBT = P + "Nbt";
    private static final String MOD = P + "Mod";
    private static final String ITEM_COUNT = P + "ItemCount";
    private static final String TAG_COUNT = P + "TagCount";
    private static final String ITEM_PREFIX = P + "Item";
    private static final String TAG_PREFIX = P + "Tag";
    private static final String ITEM_BLACK_PREFIX = P + "ItemBlack";
    private static final String TAG_BLACK_PREFIX = P + "TagBlack";
    private final QuarryMode mode;

    public QuarryCardItem(Properties properties, QuarryMode mode) { super(properties.stacksTo(1)); this.mode = mode; }
    public QuarryMode mode() { return mode; }

    @Override
    public InteractionResult use(Level level, Player player, InteractionHand hand) {
        if (!level.isClientSide() && player instanceof ServerPlayer serverPlayer) {
            int cardSlot = hand == InteractionHand.MAIN_HAND ? player.getInventory().getSelectedSlot() : Inventory.SLOT_OFFHAND;
            serverPlayer.openMenu(new SimpleMenuProvider((containerId, inventory, p) -> new QuarryFilterMenu(containerId, inventory, cardSlot), Component.translatable("gui.rftoolsbuilder.filter.title")), data -> data.writeVarInt(cardSlot));
        }
        return InteractionResult.SUCCESS;
    }

    private static CompoundTag root(ItemStack stack) {
        CustomData data = stack.get(DataComponents.CUSTOM_DATA);
        return data == null ? new CompoundTag() : data.copyTag();
    }
    private static void saveRoot(ItemStack stack, CompoundTag root) { stack.set(DataComponents.CUSTOM_DATA, CustomData.of(root)); }
    public static boolean damageMode(ItemStack stack) { return root(stack).getBooleanOr(DAMAGE, false); }
    public static boolean nbtMode(ItemStack stack) { return root(stack).getBooleanOr(NBT, false); }
    public static boolean modMode(ItemStack stack) { return root(stack).getBooleanOr(MOD, false); }
    public static int itemCount(ItemStack stack) { return Math.max(0, Math.min(MAX_FILTER_ENTRIES, root(stack).getIntOr(ITEM_COUNT, 0))); }
    public static int tagCount(ItemStack stack) { return Math.max(0, Math.min(MAX_FILTER_ENTRIES, root(stack).getIntOr(TAG_COUNT, 0))); }
    public static int entryCount(ItemStack stack) { return Math.min(MAX_FILTER_ENTRIES, itemCount(stack) + tagCount(stack)); }

    public static void toggle(ItemStack stack, int setting) {
        CompoundTag r = root(stack);
        String key = switch (setting) { case 1 -> DAMAGE; case 2 -> NBT; case 3 -> MOD; default -> null; };
        if (key == null) return;
        r.putBoolean(key, !r.getBooleanOr(key, false));
        saveRoot(stack, r);
    }

    public static String getTag(ItemStack stack, int index) {
        CompoundTag r = root(stack);
        int count = Math.max(0, Math.min(MAX_FILTER_ENTRIES, r.getIntOr(TAG_COUNT, 0)));
        if (index < 0 || index >= count) return "";
        return r.getString(TAG_PREFIX + index).orElse("");
    }

    public static ItemStack getFilterItem(ItemStack stack, int index, HolderLookup.Provider registries) {
        CompoundTag r = root(stack);
        int count = Math.max(0, Math.min(MAX_FILTER_ENTRIES, r.getIntOr(ITEM_COUNT, 0)));
        if (index < 0 || index >= count) return ItemStack.EMPTY;
        CompoundTag tag = r.getCompound(ITEM_PREFIX + index).orElse(null);
        if (tag == null) return ItemStack.EMPTY;
        return ItemStack.parseOptional(registries, tag);
    }

    public static boolean entryBlacklist(ItemStack card, int combinedIndex) {
        int tags = tagCount(card);
        if (combinedIndex < 0 || combinedIndex >= entryCount(card)) return false;
        CompoundTag r = root(card);
        boolean legacy = r.getBooleanOr(LEGACY_BLACK, false);
        return combinedIndex < tags ? r.getBooleanOr(TAG_BLACK_PREFIX + combinedIndex, legacy) : r.getBooleanOr(ITEM_BLACK_PREFIX + (combinedIndex - tags), legacy);
    }

    public static void toggleEntryRule(ItemStack card, int combinedIndex) {
        int tags = tagCount(card);
        if (combinedIndex < 0 || combinedIndex >= entryCount(card)) return;
        boolean next = !entryBlacklist(card, combinedIndex);
        CompoundTag r = root(card);
        if (combinedIndex < tags) r.putBoolean(TAG_BLACK_PREFIX + combinedIndex, next);
        else r.putBoolean(ITEM_BLACK_PREFIX + (combinedIndex - tags), next);
        saveRoot(card, r);
    }

    public static int blacklistCount(ItemStack card) { int c=0; for (int i=0;i<entryCount(card);i++) if (entryBlacklist(card,i)) c++; return c; }
    public static int whitelistCount(ItemStack card) { return entryCount(card) - blacklistCount(card); }

    public static List<String> getTags(ItemStack stack) {
        List<String> result = new ArrayList<>();
        for (int i=0;i<tagCount(stack);i++) { String value=getTag(stack,i); if (!value.isBlank()) result.add(value); }
        return result;
    }

    public static boolean addFilterItem(ItemStack card, ItemStack source, HolderLookup.Provider registries) { return addFilterItem(card, source, registries, false); }
    private static boolean addFilterItem(ItemStack card, ItemStack source, HolderLookup.Provider registries, boolean blacklist) {
        if (source.isEmpty() || source.getItem() instanceof QuarryCardItem || entryCount(card) >= MAX_FILTER_ENTRIES) return false;
        int count=itemCount(card); ItemStack normalized=source.copyWithCount(1);
        for (int i=0;i<count;i++) if (ItemStack.isSameItemSameComponents(getFilterItem(card,i,registries), normalized)) return false;
        CompoundTag r=root(card); r.put(ITEM_PREFIX+count, normalized.saveOptional(registries)); r.putBoolean(ITEM_BLACK_PREFIX+count, blacklist); r.putInt(ITEM_COUNT,count+1); saveRoot(card,r); return true;
    }

    public static boolean addFilterTag(ItemStack card, String raw) { return addFilterTag(card, raw, false); }
    private static boolean addFilterTag(ItemStack card, String raw, boolean blacklist) {
        String value=raw==null?"":raw.trim().toLowerCase(); if (value.startsWith("#")) value=value.substring(1);
        if (value.isBlank() || !value.contains(":")) return false;
        Identifier id; try { id=Identifier.parse(value); } catch (Exception e) { return false; }
        value=id.toString(); if (entryCount(card)>=MAX_FILTER_ENTRIES) return false;
        int count=tagCount(card); for (int i=0;i<count;i++) if (value.equals(getTag(card,i))) return false;
        CompoundTag r=root(card); r.putString(TAG_PREFIX+count,value); r.putBoolean(TAG_BLACK_PREFIX+count,blacklist); r.putInt(TAG_COUNT,count+1); saveRoot(card,r); return true;
    }

    public static int addTagsFromItem(ItemStack card, ItemStack source) { return addTagsFromItem(card, source, false); }
    private static int addTagsFromItem(ItemStack card, ItemStack source, boolean blacklist) {
        if (source.isEmpty()) return 0; int[] added={0};
        source.getItemHolder().tags().forEach(tag -> { if (entryCount(card)<MAX_FILTER_ENTRIES && addFilterTag(card,tag.location().toString(),blacklist)) added[0]++; });
        return added[0];
    }

    public static void removeEntry(ItemStack card, int combinedIndex, HolderLookup.Provider registries) {
        int tags=tagCount(card); if (combinedIndex<0 || combinedIndex>=entryCount(card)) return;
        CompoundTag r=root(card); boolean legacy=r.getBooleanOr(LEGACY_BLACK,false);
        if (combinedIndex<tags) {
            for (int i=combinedIndex;i<tags-1;i++) { r.putString(TAG_PREFIX+i,r.getString(TAG_PREFIX+(i+1)).orElse("")); r.putBoolean(TAG_BLACK_PREFIX+i,r.getBooleanOr(TAG_BLACK_PREFIX+(i+1),legacy)); }
            r.remove(TAG_PREFIX+(tags-1)); r.remove(TAG_BLACK_PREFIX+(tags-1)); r.putInt(TAG_COUNT,tags-1);
        } else {
            int index=combinedIndex-tags, items=itemCount(card);
            for (int i=index;i<items-1;i++) { CompoundTag next=r.getCompound(ITEM_PREFIX+(i+1)).orElse(null); if (next!=null) r.put(ITEM_PREFIX+i,next.copy()); else r.remove(ITEM_PREFIX+i); r.putBoolean(ITEM_BLACK_PREFIX+i,r.getBooleanOr(ITEM_BLACK_PREFIX+(i+1),legacy)); }
            r.remove(ITEM_PREFIX+(items-1)); r.remove(ITEM_BLACK_PREFIX+(items-1)); r.putInt(ITEM_COUNT,items-1);
        }
        saveRoot(card,r);
    }

    public static void expandEntryToTags(ItemStack card, int combinedIndex, HolderLookup.Provider registries) {
        int itemIndex=combinedIndex-tagCount(card); if (itemIndex<0 || itemIndex>=itemCount(card)) return;
        boolean blacklist=entryBlacklist(card,combinedIndex); ItemStack source=getFilterItem(card,itemIndex,registries); if (source.isEmpty()) return;
        removeEntry(card,combinedIndex,registries); addTagsFromItem(card,source,blacklist);
    }

    public static void clearFilter(ItemStack card) {
        CompoundTag r=root(card); int items=Math.max(0,r.getIntOr(ITEM_COUNT,0)), tags=Math.max(0,r.getIntOr(TAG_COUNT,0));
        for (int i=0;i<items;i++) { r.remove(ITEM_PREFIX+i); r.remove(ITEM_BLACK_PREFIX+i); }
        for (int i=0;i<tags;i++) { r.remove(TAG_PREFIX+i); r.remove(TAG_BLACK_PREFIX+i); }
        r.remove(LEGACY_BLACK); r.putInt(ITEM_COUNT,0); r.putInt(TAG_COUNT,0); saveRoot(card,r);
    }

    private static boolean matchesItemRule(ItemStack card, ItemStack target, ItemStack filter) {
        if (target.isEmpty() || filter.isEmpty()) return false;
        if (modMode(card)) { Identifier targetId=BuiltInRegistries.ITEM.getKey(target.getItem()), filterId=BuiltInRegistries.ITEM.getKey(filter.getItem()); return filterId.getNamespace().equals(targetId.getNamespace()); }
        if (filter.getItem()!=target.getItem()) return false;
        if (damageMode(card) && filter.getDamageValue()!=target.getDamageValue()) return false;
        if (nbtMode(card) && !ItemStack.isSameItemSameComponents(filter,target)) return false;
        return true;
    }

    public static boolean allowsBlock(ItemStack card, BlockState state, HolderLookup.Provider registries) {
        int items=itemCount(card), tags=tagCount(card); if (items+tags==0) return true;
        boolean hasWhitelist=whitelistCount(card)>0, matchedWhitelist=false, matchedBlacklist=false;
        ItemStack target=new ItemStack(state.getBlock().asItem());
        for (int i=0;i<tags;i++) {
            boolean match=false; try { Identifier id=Identifier.parse(getTag(card,i)); if (state.is(TagKey.create(Registries.BLOCK,id))) match=true; if (!match && !target.isEmpty() && target.is(TagKey.create(Registries.ITEM,id))) match=true; } catch (Exception ignored) { }
            if (match) { if (entryBlacklist(card,i)) matchedBlacklist=true; else matchedWhitelist=true; }
        }
        for (int i=0;i<items;i++) {
            ItemStack filter=getFilterItem(card,i,registries); if (!matchesItemRule(card,target,filter)) continue;
            if (entryBlacklist(card,tags+i)) matchedBlacklist=true; else matchedWhitelist=true;
        }
        if (matchedBlacklist) return false;
        if (matchedWhitelist) return true;
        return !hasWhitelist;
    }

    @Override
    public void appendHoverText(ItemStack stack, TooltipContext context, TooltipDisplay display, Consumer<Component> builder, TooltipFlag flag) {
        super.appendHoverText(stack, context, display, builder, flag);
        if (mode.isFortune()) builder.accept(Component.translatable("tooltip.rftoolsbuilder.fortune_iii").withStyle(ChatFormatting.GOLD));
        else if (mode.isSilk()) builder.accept(Component.translatable("tooltip.rftoolsbuilder.silk_touch").withStyle(ChatFormatting.AQUA));
        builder.accept(Component.translatable(mode.isClear()?"tooltip.rftoolsbuilder.clear_mode":"tooltip.rftoolsbuilder.replace_mode").withStyle(ChatFormatting.GRAY));
        builder.accept(Component.translatable("tooltip.rftoolsbuilder.filter_summary_mixed", whitelistCount(stack), blacklistCount(stack)).withStyle(ChatFormatting.DARK_AQUA));
        builder.accept(Component.translatable("tooltip.rftoolsbuilder.filter_open").withStyle(ChatFormatting.DARK_GRAY));
    }
}
''', encoding='utf-8')

(java / 'QuarryFilterMenu.java').write_text(r'''package mcjty.rftoolsbuilder;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
public class QuarryFilterMenu extends AbstractContainerMenu {
    public static final int REMOVE_BASE=100, EXPAND_BASE=200, TOGGLE_RULE_BASE=300;
    private final Inventory inventory; private final int cardSlot;
    public QuarryFilterMenu(int containerId, Inventory inventory, FriendlyByteBuf extraData){this(containerId,inventory,extraData.readVarInt());}
    public QuarryFilterMenu(int containerId, Inventory inventory, int cardSlot){super(RFToolsBuilder.QUARRY_FILTER_MENU.get(),containerId);this.inventory=inventory;this.cardSlot=cardSlot;int x=47,y=217;for(int row=0;row<3;row++)for(int col=0;col<9;col++)addSlot(new Slot(inventory,col+row*9+9,x+col*18,y+row*18));for(int col=0;col<9;col++)addSlot(new Slot(inventory,col,x+col*18,y+58));}
    public int cardSlot(){return cardSlot;} public ItemStack cardStack(){if(cardSlot<0||cardSlot>=inventory.getContainerSize())return ItemStack.EMPTY;return inventory.getItem(cardSlot);}
    @Override public void clicked(int slotId,int button,ContainerInput input,Player player){if(slotId>=0&&slotId<slots.size()){ItemStack source=slots.get(slotId).getItem();if(!source.isEmpty()&&!(source.getItem() instanceof QuarryCardItem)){if(!player.level().isClientSide()){if(input==ContainerInput.QUICK_MOVE)QuarryCardItem.addTagsFromItem(cardStack(),source);else QuarryCardItem.addFilterItem(cardStack(),source,player.registryAccess());broadcastChanges();}return;}}super.clicked(slotId,button,input,player);}
    @Override public boolean clickMenuButton(Player player,int id){ItemStack card=cardStack();if(!(card.getItem() instanceof QuarryCardItem))return false;if(id>=1&&id<=3){QuarryCardItem.toggle(card,id);broadcastChanges();return true;}if(id==4){QuarryCardItem.clearFilter(card);broadcastChanges();return true;}if(id>=REMOVE_BASE&&id<REMOVE_BASE+QuarryCardItem.MAX_FILTER_ENTRIES){QuarryCardItem.removeEntry(card,id-REMOVE_BASE,player.registryAccess());broadcastChanges();return true;}if(id>=EXPAND_BASE&&id<EXPAND_BASE+QuarryCardItem.MAX_FILTER_ENTRIES){QuarryCardItem.expandEntryToTags(card,id-EXPAND_BASE,player.registryAccess());broadcastChanges();return true;}if(id>=TOGGLE_RULE_BASE&&id<TOGGLE_RULE_BASE+QuarryCardItem.MAX_FILTER_ENTRIES){QuarryCardItem.toggleEntryRule(card,id-TOGGLE_RULE_BASE);broadcastChanges();return true;}return false;}
    @Override public ItemStack quickMoveStack(Player player,int index){if(index<0||index>=slots.size())return ItemStack.EMPTY;ItemStack source=slots.get(index).getItem();if(source.isEmpty()||source.getItem() instanceof QuarryCardItem)return ItemStack.EMPTY;if(!player.level().isClientSide()){QuarryCardItem.addTagsFromItem(cardStack(),source);broadcastChanges();}return source.copy();}
    @Override public boolean stillValid(Player player){return cardStack().getItem() instanceof QuarryCardItem;}
}
''', encoding='utf-8')

(java / 'BuilderMenu.java').write_text(r'''package mcjty.rftoolsbuilder;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerData;
import net.minecraft.world.inventory.SimpleContainerData;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
public class BuilderMenu extends AbstractContainerMenu {
    public static final int CONFIG_BASE=1000, CONFIG_BIAS=16_384, CONFIG_RANGE=32_769;
    private final BuilderBlockEntity builder; private final ContainerData data;
    public BuilderMenu(int containerId,Inventory playerInventory,FriendlyByteBuf extraData){this(containerId,playerInventory,(BuilderBlockEntity)playerInventory.player.level().getBlockEntity(extraData.readBlockPos()),new SimpleContainerData(12));}
    public BuilderMenu(int containerId,Inventory playerInventory,BuilderBlockEntity builder,ContainerData data){super(RFToolsBuilder.BUILDER_MENU.get(),containerId);this.builder=builder;this.data=data;addSlot(new Slot(builder,BuilderBlockEntity.SLOT_SHAPE,84,42){@Override public boolean mayPlace(ItemStack stack){return stack.getItem() instanceof ShapeCardItem;}@Override public int getMaxStackSize(){return 1;}});addSlot(new Slot(builder,BuilderBlockEntity.SLOT_QUARRY,120,42){@Override public boolean mayPlace(ItemStack stack){return stack.getItem() instanceof QuarryCardItem;}@Override public int getMaxStackSize(){return 1;}});int playerX=47,playerY=148;for(int row=0;row<3;row++)for(int col=0;col<9;col++)addSlot(new Slot(playerInventory,col+row*9+9,playerX+col*18,playerY+row*18));for(int col=0;col<9;col++)addSlot(new Slot(playerInventory,col,playerX+col*18,206));addDataSlots(data);}
    public ContainerData data(){return data;} public BuilderBlockEntity builder(){return builder;}
    @Override public boolean clickMenuButton(Player player,int id){if(builder==null)return false;if(id==0){builder.primaryAction();return true;}if(id==1){builder.stopWork();return true;}if(id>=CONFIG_BASE&&id<CONFIG_BASE+6*CONFIG_RANGE){int code=id-CONFIG_BASE,field=code/CONFIG_RANGE,value=(code%CONFIG_RANGE)-CONFIG_BIAS;if(field<3)value=Math.max(1,Math.min(512,value));else value=Math.max(-16_384,Math.min(16_384,value));builder.setConfigValue(field,value);return true;}return false;}
    @Override public ItemStack quickMoveStack(Player player,int index){if(index<0||index>=slots.size())return ItemStack.EMPTY;Slot slot=slots.get(index);if(!slot.hasItem())return ItemStack.EMPTY;ItemStack stack=slot.getItem(),copy=stack.copy();int machineSlots=2;if(index<machineSlots){if(!moveItemStackTo(stack,machineSlots,slots.size(),true))return ItemStack.EMPTY;}else if(stack.getItem() instanceof ShapeCardItem){if(!moveItemStackTo(stack,0,1,false))return ItemStack.EMPTY;}else if(stack.getItem() instanceof QuarryCardItem){if(!moveItemStackTo(stack,1,2,false))return ItemStack.EMPTY;}else return ItemStack.EMPTY;if(stack.isEmpty())slot.setByPlayer(ItemStack.EMPTY);else slot.setChanged();return copy;}
    @Override public boolean stillValid(Player player){return builder!=null&&builder.stillValid(player);}
}
''', encoding='utf-8')

# Rewrite the two GUI classes from compact templates stored below.
(client / 'BuilderScreen.java').write_text(r'''package mcjty.rftoolsbuilder.client;
import mcjty.rftoolsbuilder.BuilderBlockEntity;import mcjty.rftoolsbuilder.BuilderMenu;import net.minecraft.client.gui.GuiGraphicsExtractor;import net.minecraft.client.gui.components.Button;import net.minecraft.client.gui.components.EditBox;import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;import net.minecraft.client.input.KeyEvent;import net.minecraft.network.chat.Component;import net.minecraft.world.entity.player.Inventory;import org.lwjgl.glfw.GLFW;
public class BuilderScreen extends AbstractContainerScreen<BuilderMenu>{
private static final int BG=0xFF080C10,PANEL=0xFF131B22,PANEL_2=0xFF1A232C,BORDER=0xFF34424C,CARD_BORDER=0xFF70828F,CARD_SLOT=0xFF26343F,CYAN=0xFF19DDF2,CYAN_BRIGHT=0xFF72F4FF,CYAN_DARK=0xFF087D8C,TEXT=0xFFE7EEF2,MUTED=0xFF75838D,ORANGE=0xFFFF9B24;private final EditBox[] fields=new EditBox[6];private Button primaryButton,stopButton;private boolean syncingFields;
public BuilderScreen(BuilderMenu menu,Inventory inventory,Component title){super(menu,inventory,title,256,232);this.inventoryLabelY=139;this.titleLabelY=7;}
@Override protected void init(){super.init();primaryButton=addRenderableWidget(Button.builder(Component.empty(),b->sendButton(0)).bounds(leftPos+158,topPos+28,39,18).build());stopButton=addRenderableWidget(Button.builder(Component.literal("STOP"),b->sendButton(1)).bounds(leftPos+201,topPos+28,39,18).build());int[] xs={68,127,186,68,127,186},ys={85,85,85,111,111,111};for(int i=0;i<fields.length;i++){final int field=i;EditBox box=new EditBox(font,leftPos+xs[i],topPos+ys[i],38,16,Component.empty());box.setMaxLength(6);box.setFilter(v->v.isEmpty()||v.equals("-")||v.matches("-?\\d{0,5}"));syncingFields=true;box.setValue(Integer.toString(menu.data().get(3+i)));syncingFields=false;box.setResponder(v->{if(syncingFields||v.isEmpty()||v.equals("-"))return;try{int parsed=Integer.parseInt(v);if(field<3)parsed=Math.max(1,Math.min(512,parsed));else parsed=Math.max(-16_384,Math.min(16_384,parsed));sendConfig(field,parsed);}catch(NumberFormatException ignored){}});fields[i]=addRenderableWidget(box);}updateWidgets();}
@Override protected void containerTick(){super.containerTick();updateWidgets();syncingFields=true;for(int i=0;i<fields.length;i++)if(fields[i]!=null&&!fields[i].isFocused()){String expected=Integer.toString(menu.data().get(3+i));if(!expected.equals(fields[i].getValue()))fields[i].setValue(expected);}syncingFields=false;}
private void updateWidgets(){boolean hasShape=menu.getSlot(0).hasItem();for(EditBox field:fields)if(field!=null)field.setEditable(hasShape);int status=menu.data().get(11);boolean running=menu.data().get(2)!=0;if(primaryButton!=null)primaryButton.setMessage(Component.literal(status==BuilderBlockEntity.STATUS_PAUSED?"RESUME":running?"PAUSE":"START"));if(stopButton!=null)stopButton.active=running||status==BuilderBlockEntity.STATUS_PAUSED||menu.data().get(9)>0;}
private void sendConfig(int field,int value){sendButton(BuilderMenu.CONFIG_BASE+field*BuilderMenu.CONFIG_RANGE+(value+BuilderMenu.CONFIG_BIAS));}private void sendButton(int id){if(minecraft!=null&&minecraft.gameMode!=null)minecraft.gameMode.handleInventoryButtonClick(menu.containerId,id);}
private void panel(GuiGraphicsExtractor g,int x1,int y1,int x2,int y2){g.fill(x1,y1,x2,y2,0xFF05080B);g.fill(x1+1,y1+1,x2-1,y2-1,BORDER);g.fill(x1+2,y1+2,x2-2,y2-2,PANEL);g.fill(x1+4,y1+2,Math.min(x2-4,x1+22),y1+3,CYAN_DARK);}private static String compact(long v){if(v>=1_000_000L)return String.format(java.util.Locale.ROOT,"%.1fM",v/1_000_000.0);if(v>=1_000L)return String.format(java.util.Locale.ROOT,"%.1fK",v/1_000.0);return Long.toString(v);}private void drawEnergyBar(GuiGraphicsExtractor g,int x,int y,int e,int m){int x1=x+14,y1=y+39,x2=x+22,y2=y+65;g.fill(x1,y1,x2,y2,0xFF05080A);g.fill(x1+1,y1+1,x2-1,y2-1,BORDER);g.fill(x1+2,y1+2,x2-2,y2-2,0xFF0B151B);int inner=y2-y1-4,fill=(int)(inner*Math.min((long)e,(long)m)/Math.max(1L,(long)m));if(fill>0){g.fill(x1+2,y2-2-fill,x2-2,y2-2,CYAN);g.fill(x1+2,y2-2-fill,x2-2,Math.min(y2-2,y2-1-fill),CYAN_BRIGHT);}}private void drawCardFrame(GuiGraphicsExtractor g,int itemX,int itemY){int x1=itemX-1,y1=itemY-1,x2=itemX+17,y2=itemY+17;g.fill(x1,y1,x2,y2,0xFF05080A);g.fill(x1+1,y1+1,x2-1,y2-1,CARD_BORDER);g.fill(x1+2,y1+2,x2-2,y2-2,CARD_SLOT);}
@Override public void extractBackground(GuiGraphicsExtractor g,int mouseX,int mouseY,float partialTick){int x=leftPos,y=topPos;g.fill(x,y,x+imageWidth,y+imageHeight,BG);g.fill(x+2,y+2,x+imageWidth-2,y+imageHeight-2,PANEL_2);g.fill(x+4,y+4,x+imageWidth-4,y+imageHeight-4,BG);g.fill(x+8,y+3,x+60,y+5,CYAN_DARK);g.fill(x+imageWidth-60,y+3,x+imageWidth-8,y+5,CYAN_DARK);g.centeredText(font,Component.literal("MINER"),x+imageWidth/2,y+8,TEXT);g.fill(x+49,y+18,x+imageWidth-49,y+19,CYAN_DARK);g.fill(x+imageWidth-84,y+18,x+imageWidth-74,y+19,ORANGE);panel(g,x+8,y+22,x+66,y+72);panel(g,x+70,y+22,x+150,y+72);panel(g,x+154,y+22,x+248,y+72);int e=menu.data().get(0),m=Math.max(1,menu.data().get(1));g.text(font,Component.literal("ENERGY"),x+12,y+27,MUTED);drawEnergyBar(g,x,y,e,m);g.text(font,Component.literal(compact(e)),x+27,y+42,CYAN);g.text(font,Component.literal(((long)e*100L/m)+"%"),x+27,y+56,CYAN);g.centeredText(font,Component.literal("SHAPE"),x+92,y+27,CYAN_DARK);g.centeredText(font,Component.literal("QUARRY"),x+128,y+27,CYAN_DARK);drawCardFrame(g,x+84,y+42);drawCardFrame(g,x+120,y+42);int status=menu.data().get(11),cursor=menu.data().get(9),volume=Math.max(1,menu.data().get(10)),permille=(int)(1000L*Math.min(cursor,volume)/volume),pw=(int)(82L*Math.min(cursor,volume)/volume);g.text(font,statusText(status),x+158,y+50,CYAN);g.text(font,Component.literal((permille/10)+"."+(permille%10)+"%"),x+211,y+50,MUTED);g.fill(x+158,y+62,x+240,y+66,0xFF05080A);g.fill(x+158,y+62,x+158+pw,y+66,CYAN);panel(g,x+8,y+76,x+248,y+136);boolean shape=menu.getSlot(0).hasItem();int cc=shape?TEXT:MUTED;g.text(font,Component.literal("SIZE"),x+14,y+89,shape?CYAN_DARK:MUTED);g.text(font,Component.literal("OFFSET"),x+14,y+115,shape?CYAN_DARK:MUTED);int[] axisX={58,117,176};String[] axes={"X","Y","Z"};for(int i=0;i<3;i++){g.text(font,Component.literal(axes[i]),x+axisX[i],y+89,cc);g.text(font,Component.literal(axes[i]),x+axisX[i],y+115,cc);}g.text(font,Component.literal("Offset X/Z: até ±1024 chunks"),x+14,y+128,MUTED);panel(g,x+42,y+140,x+214,y+228);g.text(font,Component.literal("INVENTORY"),x+47,y+136,MUTED);for(int row=0;row<3;row++)for(int col=0;col<9;col++){int sx=x+46+col*18,sy=y+147+row*18;g.fill(sx,sy,sx+18,sy+18,0xFF05080A);g.fill(sx+1,sy+1,sx+17,sy+17,PANEL);}for(int col=0;col<9;col++){int sx=x+46+col*18,sy=y+205;g.fill(sx,sy,sx+18,sy+18,0xFF05080A);g.fill(sx+1,sy+1,sx+17,sy+17,PANEL);}}
private static Component statusText(int status){return switch(status){case BuilderBlockEntity.STATUS_RUNNING->Component.translatable("gui.rftoolsbuilder.status.running");case BuilderBlockEntity.STATUS_PAUSED->Component.translatable("gui.rftoolsbuilder.status.paused");case BuilderBlockEntity.STATUS_NO_CARD->Component.translatable("gui.rftoolsbuilder.status.no_card");case BuilderBlockEntity.STATUS_NO_ENERGY->Component.translatable("gui.rftoolsbuilder.status.no_energy");case BuilderBlockEntity.STATUS_OUTPUT_FULL->Component.translatable("gui.rftoolsbuilder.status.output_full");case BuilderBlockEntity.STATUS_DONE->Component.translatable("gui.rftoolsbuilder.status.done");default->Component.translatable("gui.rftoolsbuilder.status.idle");};}
@Override public boolean keyPressed(KeyEvent event){for(EditBox field:fields)if(field!=null&&field.isFocused()){if(field.keyPressed(event))return true;if(event.key()!=GLFW.GLFW_KEY_TAB&&event.key()!=GLFW.GLFW_KEY_ESCAPE)return true;break;}return super.keyPressed(event);}@Override protected void extractLabels(GuiGraphicsExtractor graphics,int mouseX,int mouseY){}
}
''',encoding='utf-8')

(client / 'QuarryFilterScreen.java').write_text(r'''package mcjty.rftoolsbuilder.client;
import mcjty.rftoolsbuilder.FilterTagPayload;import mcjty.rftoolsbuilder.QuarryCardItem;import mcjty.rftoolsbuilder.QuarryFilterMenu;import net.minecraft.client.gui.GuiGraphicsExtractor;import net.minecraft.client.gui.components.Button;import net.minecraft.client.gui.components.EditBox;import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;import net.minecraft.client.input.KeyEvent;import net.minecraft.client.input.MouseButtonEvent;import net.minecraft.network.chat.Component;import net.minecraft.world.entity.player.Inventory;import net.minecraft.world.item.ItemStack;import net.neoforged.neoforge.client.network.ClientPacketDistributor;import org.lwjgl.glfw.GLFW;
public class QuarryFilterScreen extends AbstractContainerScreen<QuarryFilterMenu>{private static final int BG=0xFF080C10,PANEL=0xFF111820,PANEL_2=0xFF18222B,BORDER=0xFF33434E,CYAN=0xFF18DDF3,CYAN_DARK=0xFF087A88,ORANGE=0xFFFF9B24,TEXT=0xFFE8F1F4,MUTED=0xFF74838D,SELECTED=0xFF17333D,VISIBLE_ROWS=5;private int selected=-1,scroll=0;private Button ruleButton,damageButton,nbtButton,modButton,removeButton,expandButton,upButton,downButton;private EditBox tagBox;public QuarryFilterScreen(QuarryFilterMenu menu,Inventory inventory,Component title){super(menu,inventory,title,256,304);this.inventoryLabelY=204;this.titleLabelY=7;}
@Override protected void init(){super.init();ruleButton=addRenderableWidget(Button.builder(Component.empty(),b->toggleSelectedRule()).bounds(leftPos+8,topPos+24,74,18).build());modButton=addRenderableWidget(Button.builder(Component.empty(),b->send(3)).bounds(leftPos+84,topPos+24,50,18).build());nbtButton=addRenderableWidget(Button.builder(Component.empty(),b->send(2)).bounds(leftPos+136,topPos+24,54,18).build());damageButton=addRenderableWidget(Button.builder(Component.empty(),b->send(1)).bounds(leftPos+192,topPos+24,56,18).build());tagBox=new EditBox(font,leftPos+8,topPos+48,180,16,Component.literal("Tag"));tagBox.setMaxLength(80);tagBox.setHint(Component.literal("c:ores"));addRenderableWidget(tagBox);addRenderableWidget(Button.builder(Component.literal("+ TAG"),b->addTag()).bounds(leftPos+190,topPos+48,58,16).build());upButton=addRenderableWidget(Button.builder(Component.literal("▲"),b->{if(scroll>0)scroll--;}).bounds(leftPos+228,topPos+82,20,18).build());downButton=addRenderableWidget(Button.builder(Component.literal("▼"),b->{int max=Math.max(0,QuarryCardItem.entryCount(card())-VISIBLE_ROWS);if(scroll<max)scroll++;}).bounds(leftPos+228,topPos+144,20,18).build());removeButton=addRenderableWidget(Button.builder(Component.literal("REMOVE"),b->{if(selected>=0)send(QuarryFilterMenu.REMOVE_BASE+selected);}).bounds(leftPos+8,topPos+174,64,18).build());expandButton=addRenderableWidget(Button.builder(Component.literal("EXPAND"),b->{if(selected>=0)send(QuarryFilterMenu.EXPAND_BASE+selected);}).bounds(leftPos+74,topPos+174,64,18).build());addRenderableWidget(Button.builder(Component.literal("CLEAR"),b->{selected=-1;scroll=0;send(4);}).bounds(leftPos+184,topPos+174,64,18).build());syncButtons();}
private void addTag(){String value=tagBox.getValue().trim();if(value.isEmpty())return;ClientPacketDistributor.sendToServer(new FilterTagPayload(menu.cardSlot(),value));tagBox.setValue("");selected=-1;}private void toggleSelectedRule(){if(selected>=0)send(QuarryFilterMenu.TOGGLE_RULE_BASE+selected);}private void send(int id){if(minecraft!=null&&minecraft.gameMode!=null)minecraft.gameMode.handleInventoryButtonClick(menu.containerId,id);}private ItemStack card(){return menu.cardStack();}
private String entryLabel(int combined){int tags=QuarryCardItem.tagCount(card());if(combined<tags)return "#"+QuarryCardItem.getTag(card(),combined);if(minecraft==null||minecraft.level==null)return "";ItemStack item=QuarryCardItem.getFilterItem(card(),combined-tags,minecraft.level.registryAccess());return item.isEmpty()?"":item.getHoverName().getString();}private ItemStack entryItem(int combined){int tags=QuarryCardItem.tagCount(card());if(combined<tags||minecraft==null||minecraft.level==null)return ItemStack.EMPTY;return QuarryCardItem.getFilterItem(card(),combined-tags,minecraft.level.registryAccess());}
private void syncButtons(){int count=QuarryCardItem.entryCount(card()),tags=QuarryCardItem.tagCount(card());if(selected>=count)selected=-1;int maxScroll=Math.max(0,count-VISIBLE_ROWS);if(scroll>maxScroll)scroll=maxScroll;if(ruleButton!=null){ruleButton.active=selected>=0;ruleButton.setMessage(Component.literal(selected<0?"RULE: —":QuarryCardItem.entryBlacklist(card(),selected)?"RULE: BLACK":"RULE: WHITE"));}modButton.setMessage(Component.literal(QuarryCardItem.modMode(card())?"MOD: ON":"MOD: OFF"));nbtButton.setMessage(Component.literal(QuarryCardItem.nbtMode(card())?"DATA: ON":"DATA: OFF"));damageButton.setMessage(Component.literal(QuarryCardItem.damageMode(card())?"DMG: ON":"DMG: OFF"));removeButton.active=selected>=0;expandButton.active=selected>=tags&&selected<count;upButton.active=scroll>0;downButton.active=scroll<maxScroll;}
@Override protected void containerTick(){super.containerTick();syncButtons();}@Override public boolean mouseClicked(MouseButtonEvent event,boolean doubleClick){int lx=(int)event.x()-leftPos,ly=(int)event.y()-topPos;if(lx>=9&&lx<224&&ly>=82&&ly<162){int row=(ly-82)/16;if(row>=0&&row<VISIBLE_ROWS){int idx=scroll+row;if(idx<QuarryCardItem.entryCount(card())){selected=idx;return true;}}}return super.mouseClicked(event,doubleClick);}private void panel(GuiGraphicsExtractor g,int x1,int y1,int x2,int y2){g.fill(x1,y1,x2,y2,0xFF05080B);g.fill(x1+1,y1+1,x2-1,y2-1,BORDER);g.fill(x1+2,y1+2,x2-2,y2-2,PANEL);g.fill(x1+4,y1+2,Math.min(x2-4,x1+28),y1+3,CYAN_DARK);}
@Override public void extractBackground(GuiGraphicsExtractor g,int mouseX,int mouseY,float partialTick){int x=leftPos,y=topPos;g.fill(x,y,x+imageWidth,y+imageHeight,BG);g.fill(x+2,y+2,x+imageWidth-2,y+imageHeight-2,PANEL_2);g.fill(x+4,y+4,x+imageWidth-4,y+imageHeight-4,BG);g.fill(x+8,y+3,x+64,y+5,CYAN_DARK);g.fill(x+imageWidth-64,y+3,x+imageWidth-8,y+5,CYAN_DARK);g.centeredText(font,Component.literal("QUARRY CARD FILTER"),x+imageWidth/2,y+8,TEXT);panel(g,x+6,y+20,x+250,y+68);panel(g,x+6,y+72,x+250,y+170);panel(g,x+6,y+170,x+250,y+198);panel(g,x+42,y+204,x+214,y+300);int count=QuarryCardItem.entryCount(card());g.text(font,Component.literal("FILTER LIST  "+count+"/18"),x+10,y+73,CYAN_DARK);for(int row=0;row<VISIBLE_ROWS;row++){int idx=scroll+row,ry=y+82+row*16;g.fill(x+9,ry,x+224,ry+15,idx==selected?SELECTED:0xFF0A1015);g.fill(x+9,ry,x+10,ry+15,idx==selected?CYAN:BORDER);if(idx<count){boolean black=QuarryCardItem.entryBlacklist(card(),idx);g.fill(x+13,ry+2,x+28,ry+13,black?0xFF4B2515:0xFF103842);g.centeredText(font,Component.literal(black?"B":"W"),x+20,ry+3,black?ORANGE:CYAN);ItemStack icon=entryItem(idx);int tx=x+34;if(!icon.isEmpty()){g.item(icon,x+32,ry-1);tx=x+51;}String label=entryLabel(idx);if(label.length()>25)label=label.substring(0,24)+"…";g.text(font,Component.literal(label),tx,ry+3,TEXT);}}g.text(font,Component.literal("W = whitelist  •  B = blacklist (B vence)"),x+9,y+199,MUTED);g.text(font,Component.literal("INVENTORY"),x+47,y+205,CYAN_DARK);for(int row=0;row<3;row++)for(int col=0;col<9;col++){int sx=x+46+col*18,sy=y+216+row*18;g.fill(sx,sy,sx+18,sy+18,0xFF05080A);g.fill(sx+1,sy+1,sx+17,sy+17,PANEL);}for(int col=0;col<9;col++){int sx=x+46+col*18,sy=y+274;g.fill(sx,sy,sx+18,sy+18,0xFF05080A);g.fill(sx+1,sy+1,sx+17,sy+17,PANEL);}}
@Override public boolean keyPressed(KeyEvent event){if(tagBox!=null&&tagBox.isFocused()){if(tagBox.keyPressed(event))return true;if(event.key()!=GLFW.GLFW_KEY_TAB&&event.key()!=GLFW.GLFW_KEY_ESCAPE)return true;}return super.keyPressed(event);}@Override protected void extractLabels(GuiGraphicsExtractor g,int mouseX,int mouseY){}
}
''',encoding='utf-8')

def png(path,px):
    raw=b''.join(b'\x00'+bytes(sum(row,())) for row in px)
    def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',16,16,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b''))
T=(0,0,0,0);DARK=(24,30,37,255);MID=(43,52,62,255);EDGE=(127,142,154,255);HI=(210,220,226,255);WHITE=(235,240,243,255);OR=(255,137,15,255);GOLD=(255,190,38,255);CY=(40,220,244,255);CYHI=(166,248,255,255)
def base(accent):
    px=[[T for _ in range(16)] for _ in range(16)]
    for y in range(1,15):
        for x in range(1,15):px[y][x]=DARK
    for x in range(2,14):px[1][x]=EDGE;px[14][x]=EDGE
    for y in range(2,14):px[y][1]=EDGE;px[y][14]=EDGE
    for x in range(2,14):px[2][x]=MID
    for x in range(3,13):px[3][x]=accent
    for x in range(3,13,2):px[13][x]=(199,151,59,255)
    px[1][1]=px[1][14]=px[14][1]=px[14][14]=HI
    return px
def line(px,pts,c):
    for x,y in pts:
        if 0<=x<16 and 0<=y<16:px[y][x]=c
def shape_card():
    px=base(OR);line(px,[(4,7),(5,6),(6,6),(7,6),(8,7),(8,8),(8,9),(7,10),(6,10),(5,10),(4,9),(4,8)],WHITE);line(px,[(7,5),(8,4),(9,4),(10,4),(11,5),(11,6),(11,7),(10,8),(9,8)],OR);line(px,[(5,6),(8,4),(8,7),(11,5),(8,9),(10,8)],OR);px[8][6]=OR;px[7][7]=OR;return px
def quarry_card(accent=OR,badge=None,clear=False):
    px=base(accent);line(px,[(5,11),(6,10),(7,9),(8,8),(9,7),(10,6)],WHITE);line(px,[(7,5),(8,5),(9,5),(10,5),(11,6),(12,6)],accent);line(px,[(6,6),(7,5),(8,6)],HI)
    if badge=='fortune':line(px,[(11,9),(11,11),(10,10),(12,10)],GOLD);px[10][11]=WHITE
    elif badge=='silk':line(px,[(11,9),(12,10),(11,11),(10,10)],CY);px[10][11]=CYHI
    if clear:line(px,[(3,10),(4,11),(3,12),(4,10),(3,11),(4,12)],WHITE)
    return px
textures=res/'assets/rftoolsbuilder/textures/item';textures.mkdir(parents=True,exist_ok=True)
for name,pixels in {'shapecarditem.png':shape_card(),'shapecardquarryitem.png':quarry_card(OR),'shapecardcquarryitem.png':quarry_card(WHITE,clear=True),'shapecardfortuneitem.png':quarry_card(GOLD,'fortune'),'shapecardcfortuneitem.png':quarry_card(GOLD,'fortune',True),'shapecardsilkitem.png':quarry_card(CY,'silk'),'shapecardcsilkitem.png':quarry_card(CY,'silk',True)}.items():png(textures/name,pixels)

import json
for lang_name in ('pt_br.json','en_us.json'):
    lp=res/'assets/rftoolsbuilder/lang'/lang_name;lang=json.loads(lp.read_text(encoding='utf-8'));lang['block.rftoolsbuilder.builder']='Miner';lang['gui.rftoolsbuilder.status.paused']='Pausado' if lang_name=='pt_br.json' else 'Paused';lang['tooltip.rftoolsbuilder.filter_summary_mixed']='Filtro: %s whitelist / %s blacklist' if lang_name=='pt_br.json' else 'Filter: %s whitelist / %s blacklist';lp.write_text(json.dumps(lang,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
build=root/'build.gradle';bs=build.read_text(encoding='utf-8');bs,n=re.subn(r"(?m)^version\s*=\s*['\"]3\.0\.4['\"]","version = '3.0.5'",bs,count=1)
if n!=1:raise SystemExit('3.0.4 version not found')
build.write_text(bs,encoding='utf-8')
print('Quantum Tools 3.0.5 applied')

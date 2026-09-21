import java.nio.file.Files;
import java.nio.file.Path;
import org.objectweb.asm.*;

/** Android-only DEX input: Flow 25.2.9 initializes a virtual-thread pool even in production. */
public class AndroidVaadinBytecode {
    public static void main(String[] args) throws Exception {
        Path file = Path.of(args[0]);
        ClassReader reader = new ClassReader(Files.readAllBytes(file));
        if (!reader.getClassName().equals("com/vaadin/flow/internal/FrontendUtils")) {
            throw new IllegalArgumentException("Expected FrontendUtils");
        }
        ClassWriter writer = new ClassWriter(0);
        int[] replaced = {0};
        reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String descriptor,
                    String signature, String[] exceptions) {
                MethodVisitor next = super.visitMethod(access, name, descriptor, signature, exceptions);
                if (!name.equals("<clinit>")) return next;
                return new MethodVisitor(Opcodes.ASM9, next) {
                    @Override
                    public void visitMethodInsn(int opcode, String owner, String name, String descriptor, boolean itf) {
                        if (owner.equals("java/lang/Thread") && name.equals("ofVirtual")) {
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, "java/util/concurrent/Executors",
                                    "defaultThreadFactory", "()Ljava/util/concurrent/ThreadFactory;", false);
                        } else if (owner.equals("java/lang/Thread$Builder$OfVirtual") && name.equals("name")
                                && descriptor.equals("(Ljava/lang/String;J)Ljava/lang/Thread$Builder$OfVirtual;")) {
                            super.visitInsn(Opcodes.POP2); // counter
                            super.visitInsn(Opcodes.POP); // prefix; keep the platform ThreadFactory
                        } else if (owner.equals("java/lang/Thread$Builder$OfVirtual") && name.equals("factory")) {
                            // The platform ThreadFactory is already on the stack.
                        } else if (owner.equals("java/util/concurrent/Executors") && name.equals("newThreadPerTaskExecutor")) {
                            super.visitMethodInsn(opcode, owner, "newCachedThreadPool", descriptor, itf);
                        } else {
                            super.visitMethodInsn(opcode, owner, name, descriptor, itf);
                            return;
                        }
                        replaced[0]++;
                    }
                };
            }
        }, 0);
        if (replaced[0] != 4) throw new IllegalStateException("Flow changed: expected 4 virtual-thread calls, got " + replaced[0]);
        Files.write(file, writer.toByteArray());
    }
}
